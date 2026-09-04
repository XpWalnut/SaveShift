from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
import webbrowser

from app.coordination.errors import CoordinationError, CoordinationUnavailableError
from app.coordination.cloudflare_config import (
    CLOUDFLARE_OAUTH_CLIENT_ID,
    CLOUDFLARE_OAUTH_SCOPES,
)
from app.coordination.http_provider import HttpCoordinationProvider
from app.coordination.models import PairedDevice
from app.version import APP_VERSION


OAUTH_USER_AGENT = f"SaveShift/{APP_VERSION} OAuth-PKCE"


class CloudflareProvisioningError(CoordinationError):
    """Cloudflare authorization or provider provisioning failed."""


@dataclass(frozen=True)
class CloudflareOAuthConfig:
    client_id: str
    redirect_uri: str = "http://127.0.0.1:43917/oauth/callback"
    scopes: tuple[str, ...] = ()

    AUTHORIZATION_ENDPOINT = "https://dash.cloudflare.com/oauth2/auth"
    TOKEN_ENDPOINT = "https://dash.cloudflare.com/oauth2/token"
    REVOKE_ENDPOINT = "https://dash.cloudflare.com/oauth2/revoke"

    @classmethod
    def from_environment(cls) -> "CloudflareOAuthConfig":
        configured_scopes = os.environ.get("SAVESHIFT_CLOUDFLARE_OAUTH_SCOPES")
        scopes = (
            tuple(scope for scope in configured_scopes.split() if scope)
            if configured_scopes is not None
            else CLOUDFLARE_OAUTH_SCOPES
        )
        return cls(
            client_id=os.environ.get(
                "SAVESHIFT_CLOUDFLARE_OAUTH_CLIENT_ID",
                CLOUDFLARE_OAUTH_CLIENT_ID,
            ).strip(),
            redirect_uri=os.environ.get(
                "SAVESHIFT_CLOUDFLARE_OAUTH_REDIRECT_URI",
                cls.redirect_uri,
            ).strip(),
            scopes=scopes,
        )

    @property
    def available(self) -> bool:
        return bool(self.client_id)


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str = ""


@dataclass(frozen=True)
class CloudflareAccount:
    account_id: str
    name: str


@dataclass(frozen=True)
class ProvisionedProvider:
    provider_url: str
    account_id: str
    script_name: str
    bootstrap_token: str


@dataclass(frozen=True)
class CreatedGroup:
    provider_url: str
    account_id: str
    script_name: str
    device: PairedDevice


class CloudflareOAuthClient:
    def __init__(
        self,
        config: CloudflareOAuthConfig,
        *,
        timeout_seconds: float = 180.0,
        browser_open: Callable[[str], bool] = webbrowser.open,
        urlopen_function: Callable[..., Any] = urlopen,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.browser_open = browser_open
        self.urlopen = urlopen_function

    def authorize(
        self,
        *,
        completion_heading: str = "Cloudflare authorization complete",
        completion_message: str = (
            "Save Shift is finishing group setup. You may close this tab "
            "and return to the app."
        ),
    ) -> OAuthTokens:
        if not self.config.available:
            raise CloudflareProvisioningError(
                "Cloudflare group creation is not configured in this build."
            )

        verifier = secrets.token_urlsafe(64)
        challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(32)
        parameters = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }

        if self.config.scopes:
            parameters["scope"] = " ".join(self.config.scopes)

        authorization_url = (
            f"{self.config.AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"
        )
        callback = _OAuthCallbackReceiver(
            redirect_uri=self.config.redirect_uri,
            expected_state=state,
            timeout_seconds=self.timeout_seconds,
            completion_heading=completion_heading,
            completion_message=completion_message,
        )

        code = callback.wait_for_code(
            lambda: self.browser_open(authorization_url)
        )
        return self._exchange_code(code, verifier)

    def revoke(self, access_token: str) -> None:
        body = urlencode(
            {
                "token": access_token,
                "client_id": self.config.client_id,
            }
        ).encode("ascii")
        request = Request(
            self.config.REVOKE_ENDPOINT,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": OAUTH_USER_AGENT,
            },
            method="POST",
        )

        try:
            with self.urlopen(request, timeout=10.0):
                return
        except (HTTPError, URLError, OSError, TimeoutError):
            return

    def _exchange_code(self, code: str, verifier: str) -> OAuthTokens:
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self.config.client_id,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
                "code_verifier": verifier,
            }
        ).encode("ascii")
        request = Request(
            self.config.TOKEN_ENDPOINT,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": OAUTH_USER_AGENT,
            },
            method="POST",
        )

        try:
            with self.urlopen(request, timeout=15.0) as response:
                data = _read_json(response.read())
        except HTTPError as error:
            raise CloudflareProvisioningError(
                _oauth_http_message(error)
            ) from error
        except (URLError, OSError, TimeoutError) as error:
            raise CloudflareProvisioningError(
                "Cloudflare could not be reached during authorization."
            ) from error

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token", "")

        if not isinstance(access_token, str) or not access_token:
            raise CloudflareProvisioningError(
                "Cloudflare did not return an access token."
            )
        if not isinstance(refresh_token, str):
            refresh_token = ""

        return OAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
        )


class CloudflareApiClient:
    API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        access_token: str,
        *,
        timeout_seconds: float = 20.0,
        urlopen_function: Callable[..., Any] = urlopen,
    ) -> None:
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen_function

    def list_accounts(self) -> list[CloudflareAccount]:
        data = self._request_json(
            "GET",
            "/memberships?status=accepted&per_page=50",
        )
        result = data.get("result")

        if not isinstance(result, list):
            raise CloudflareProvisioningError(
                "Cloudflare returned an invalid account list."
            )

        accounts: list[CloudflareAccount] = []

        for item in result:
            if not isinstance(item, dict):
                continue
            account = item.get("account")

            if not isinstance(account, dict):
                continue

            account_id = account.get("id")
            name = account.get("name")

            if isinstance(account_id, str) and isinstance(name, str):
                accounts.append(CloudflareAccount(account_id, name))

        return accounts

    def get_workers_subdomain(self, account_id: str) -> str | None:
        data = self._request_json(
            "GET",
            f"/accounts/{quote(account_id, safe='')}/workers/subdomain",
            allow_missing=True,
        )

        if data is None:
            return None

        result = data.get("result")
        subdomain = result.get("subdomain") if isinstance(result, dict) else None
        return subdomain if isinstance(subdomain, str) and subdomain else None

    def create_workers_subdomain(self, account_id: str, subdomain: str) -> str:
        data = self._request_json(
            "PUT",
            f"/accounts/{quote(account_id, safe='')}/workers/subdomain",
            payload={"subdomain": subdomain},
        )
        result = data.get("result")
        created = result.get("subdomain") if isinstance(result, dict) else None

        if not isinstance(created, str) or not created:
            raise CloudflareProvisioningError(
                "Cloudflare did not create a workers.dev address."
            )

        return created

    def upload_worker(
        self,
        account_id: str,
        script_name: str,
        module: bytes,
        bootstrap_token: str,
    ) -> None:
        metadata = {
            "main_module": "index.js",
            "compatibility_date": "2026-07-14",
            "compatibility_flags": ["nodejs_compat"],
            "bindings": [
                {
                    "type": "durable_object_namespace",
                    "name": "COORDINATION",
                    "class_name": "CoordinationGroup",
                },
                {
                    "type": "plain_text",
                    "name": "LEASE_SECONDS",
                    "text": "900",
                },
                {
                    "type": "secret_text",
                    "name": "ADMIN_BOOTSTRAP_TOKEN",
                    "text": bootstrap_token,
                },
            ],
            "migrations": {
                "new_tag": "v1",
                "new_sqlite_classes": ["CoordinationGroup"],
            },
        }
        boundary = f"saveshift-{secrets.token_hex(16)}"
        body = _multipart_body(
            boundary,
            metadata=json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
            module=module,
        )
        self._request_json(
            "PUT",
            (
                f"/accounts/{quote(account_id, safe='')}/workers/scripts/"
                f"{quote(script_name, safe='')}"
            ),
            raw_body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def enable_worker_subdomain(self, account_id: str, script_name: str) -> None:
        self._request_json(
            "POST",
            (
                f"/accounts/{quote(account_id, safe='')}/workers/scripts/"
                f"{quote(script_name, safe='')}/subdomain"
            ),
            payload={"enabled": True, "previews_enabled": False},
        )

    def delete_worker(self, account_id: str, script_name: str) -> None:
        self._request_json(
            "DELETE",
            (
                f"/accounts/{quote(account_id, safe='')}/workers/scripts/"
                f"{quote(script_name, safe='')}?force=true"
            ),
            allow_empty=True,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        raw_body: bytes | None = None,
        content_type: str = "application/json",
        allow_missing: bool = False,
        allow_empty: bool = False,
    ) -> dict[str, Any] | None:
        body = raw_body

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(
            f"{self.API_BASE}{path}",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": content_type,
                "User-Agent": "SaveShift-Cloudflare-Provisioner/1",
            },
            method=method,
        )

        try:
            with self.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
                data = (
                    {}
                    if allow_empty and not response_body
                    else _read_json(response_body)
                )
        except HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            raise CloudflareProvisioningError(_cloudflare_http_message(error)) from error
        except (URLError, OSError, TimeoutError) as error:
            raise CloudflareProvisioningError(
                "Cloudflare could not be reached while creating the group."
            ) from error

        if data.get("success") is False:
            raise CloudflareProvisioningError(_cloudflare_error_message(data))

        return data


class CloudflareProviderProvisioner:
    def __init__(
        self,
        api: CloudflareApiClient,
        *,
        worker_module_path: Path | None = None,
        health_check: Callable[[str], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api = api
        self.worker_module_path = worker_module_path or _worker_module_path()
        self.health_check = health_check or self._provider_is_healthy
        self.sleep = sleep

    def provision(self, account_id: str) -> ProvisionedProvider:
        try:
            module = self.worker_module_path.read_bytes()
        except OSError as error:
            raise CloudflareProvisioningError(
                "The bundled coordination provider is missing from this installation."
            ) from error

        subdomain = self.api.get_workers_subdomain(account_id)

        if not subdomain:
            subdomain = self.api.create_workers_subdomain(
                account_id,
                f"saveshift-{secrets.token_hex(4)}",
            )

        script_name = f"saveshift-coordination-{secrets.token_hex(3)}"
        bootstrap_token = secrets.token_urlsafe(32)
        self.api.upload_worker(
            account_id,
            script_name,
            module,
            bootstrap_token,
        )
        self.api.enable_worker_subdomain(account_id, script_name)

        provider_url = f"https://{script_name}.{subdomain}.workers.dev"

        for attempt in range(5):
            if self.health_check(provider_url):
                break

            if attempt < 4:
                self.sleep(0.5)
        else:
            raise CloudflareProvisioningError(
                "The coordination provider was deployed but did not become ready."
            )

        return ProvisionedProvider(
            provider_url=provider_url,
            account_id=account_id,
            script_name=script_name,
            bootstrap_token=bootstrap_token,
        )

    @staticmethod
    def _provider_is_healthy(provider_url: str) -> bool:
        try:
            health = HttpCoordinationProvider(provider_url).health()
        except CoordinationError:
            return False

        return health.get("status") == "ok" and health.get("api_version") == "v1"


class CloudflareGroupCreator:
    def __init__(
        self,
        oauth: CloudflareOAuthClient,
        *,
        api_factory: Callable[[str], CloudflareApiClient] = CloudflareApiClient,
        provisioner_factory: Callable[
            [CloudflareApiClient], CloudflareProviderProvisioner
        ] = CloudflareProviderProvisioner,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.oauth = oauth
        self.api_factory = api_factory
        self.provisioner_factory = provisioner_factory
        self.sleep = sleep

    def create_group(self, device_name: str) -> CreatedGroup:
        tokens = self.oauth.authorize()

        try:
            api = self.api_factory(tokens.access_token)
            accounts = api.list_accounts()

            if not accounts:
                raise CloudflareProvisioningError(
                    "Cloudflare did not provide an account for deployment."
                )
            if len(accounts) > 1:
                raise CloudflareProvisioningError(
                    "More than one Cloudflare account was authorized. "
                    "Authorize only the account that should own this group."
                )

            provisioned = self.provisioner_factory(api).provision(
                accounts[0].account_id
            )
            provider = HttpCoordinationProvider(provisioned.provider_url)
            device = self._bootstrap_with_retry(provider, provisioned, device_name)
            return CreatedGroup(
                provider_url=provisioned.provider_url,
                account_id=provisioned.account_id,
                script_name=provisioned.script_name,
                device=device,
            )
        finally:
            self.oauth.revoke(tokens.access_token)
            if tokens.refresh_token:
                self.oauth.revoke(tokens.refresh_token)

    def _bootstrap_with_retry(
        self,
        provider: HttpCoordinationProvider,
        provisioned: ProvisionedProvider,
        device_name: str,
    ) -> PairedDevice:
        retry_delays = (0.5, 1.0, 2.0, 3.0, 4.0)

        for delay in (*retry_delays, None):
            try:
                return provider.bootstrap(
                    provisioned.bootstrap_token,
                    device_name,
                )
            except CoordinationUnavailableError:
                if delay is None:
                    raise
                self.sleep(delay)

        raise AssertionError("Bootstrap retry loop did not return or raise.")


class CloudflareWorkerRemover:
    def __init__(
        self,
        oauth: CloudflareOAuthClient,
        *,
        api_factory: Callable[[str], CloudflareApiClient] = CloudflareApiClient,
    ) -> None:
        self.oauth = oauth
        self.api_factory = api_factory

    def remove(self, account_id: str, script_name: str) -> None:
        tokens = self.oauth.authorize(
            completion_heading="Group removal authorized",
            completion_message=(
                "Save Shift is finishing group removal. You may close this tab "
                "and return to the app."
            ),
        )

        try:
            api = self.api_factory(tokens.access_token)
            authorized_accounts = {
                account.account_id for account in api.list_accounts()
            }

            if account_id not in authorized_accounts:
                raise CloudflareProvisioningError(
                    "Authorize the Cloudflare account that owns this Save Shift group."
                )

            api.delete_worker(account_id, script_name)
        finally:
            self.oauth.revoke(tokens.access_token)
            if tokens.refresh_token:
                self.oauth.revoke(tokens.refresh_token)


class _OAuthCallbackReceiver:
    def __init__(
        self,
        *,
        redirect_uri: str,
        expected_state: str,
        timeout_seconds: float,
        completion_heading: str,
        completion_message: str,
    ) -> None:
        parsed = urlparse(redirect_uri)

        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise CloudflareProvisioningError(
                "The Cloudflare OAuth callback must use 127.0.0.1 with a fixed port."
            )

        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/"
        self.expected_state = expected_state
        self.timeout_seconds = timeout_seconds
        self.completion_heading = completion_heading
        self.completion_message = completion_message

    def wait_for_code(self, open_authorization: Callable[[], bool]) -> str:
        result: dict[str, str] = {}
        expected_path = self.path
        expected_state = self.expected_state
        completion_heading = self.completion_heading
        completion_message = self.completion_message

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                parameters = parse_qs(parsed.query)

                if parsed.path != expected_path:
                    self.send_error(404)
                    return

                state = parameters.get("state", [""])[0]
                code = parameters.get("code", [""])[0]
                error = parameters.get("error_description", [""])[0]

                if state != expected_state:
                    result["error"] = "Cloudflare returned an invalid authorization state."
                    self._respond(
                        "Authorization could not be verified",
                        "Return to Save Shift and try again.",
                        400,
                    )
                elif error:
                    result["error"] = error
                    self._respond(
                        "Authorization was cancelled",
                        "No Cloudflare changes were made. You may close this tab.",
                        400,
                    )
                elif not code:
                    result["error"] = "Cloudflare did not return an authorization code."
                    self._respond(
                        "Authorization did not complete",
                        "Return to Save Shift and try again.",
                        400,
                    )
                else:
                    result["code"] = code
                    self._respond(
                        completion_heading,
                        completion_message,
                        200,
                    )

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _respond(self, heading: str, message: str, status: int) -> None:
                body = _oauth_callback_page(
                    heading,
                    message,
                    successful=status < 400,
                )
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'",
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            server = HTTPServer((self.host, self.port), Handler)
        except OSError as error:
            raise CloudflareProvisioningError(
                "Save Shift could not start its local Cloudflare callback."
            ) from error

        try:
            if not open_authorization():
                raise CloudflareProvisioningError(
                    "Save Shift could not open the Cloudflare authorization page."
                )
            deadline = time.monotonic() + self.timeout_seconds

            while "code" not in result and "error" not in result:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    break

                server.timeout = min(1.0, remaining)
                server.handle_request()
        finally:
            server.server_close()

        if "error" in result:
            raise CloudflareProvisioningError(result["error"])
        if "code" not in result:
            raise CloudflareProvisioningError(
                "Cloudflare authorization timed out."
            )

        return result["code"]


def _worker_module_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "app" / "resources" / "cloudflare" / "index.js"


def _oauth_callback_page(
    heading: str,
    message: str,
    *,
    successful: bool,
) -> bytes:
    safe_heading = html.escape(heading)
    safe_message = html.escape(message)
    symbol = "✓" if successful else "!"
    state_class = "success" if successful else "error"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_heading} · Save Shift</title>
  <style>
    :root {{ color-scheme: dark; font-family: "Segoe UI", system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{
      min-height: 100vh; margin: 0; display: grid; place-items: center;
      color: #f5f7ff; background: #1d1f23;
    }}
    main {{
      width: min(520px, calc(100% - 32px)); padding: 36px;
      background: #292c31; border: 1px solid #3b3f47; border-radius: 16px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, .35); text-align: center;
    }}
    .brand {{ color: #b9c2e8; font-size: 14px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    .status {{
      width: 64px; height: 64px; margin: 24px auto; display: grid;
      place-items: center; border-radius: 50%; font-size: 34px; font-weight: 700;
    }}
    .status.success {{ background: #5667b4; }}
    .status.error {{ background: #a94442; }}
    h1 {{ margin: 0 0 14px; font-size: 28px; line-height: 1.2; }}
    p {{ margin: 0; color: #c8ccda; font-size: 16px; line-height: 1.6; }}
  </style>
</head>
<body>
  <main>
    <div class="brand">Save Shift</div>
    <div class="status {state_class}" aria-hidden="true">{symbol}</div>
    <h1>{safe_heading}</h1>
    <p>{safe_message}</p>
  </main>
</body>
</html>""".encode("utf-8")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _read_json(value: bytes) -> dict[str, Any]:
    try:
        data = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloudflareProvisioningError(
            "Cloudflare returned an invalid response."
        ) from error

    if not isinstance(data, dict):
        raise CloudflareProvisioningError(
            "Cloudflare returned an invalid response."
        )

    return data


def _cloudflare_http_message(error: HTTPError) -> str:
    try:
        data = _read_json(error.read())
    except CloudflareProvisioningError:
        return f"Cloudflare returned HTTP {error.code} during group setup."

    return _cloudflare_error_message(data)


def _oauth_http_message(error: HTTPError) -> str:
    try:
        data = _read_json(error.read())
    except CloudflareProvisioningError:
        return f"Cloudflare rejected the authorization request (HTTP {error.code})."

    description = data.get("error_description")
    code = data.get("error")

    if isinstance(description, str) and description.strip():
        return f"Cloudflare authorization failed: {description.strip()}"
    if isinstance(code, str) and code.strip():
        return f"Cloudflare authorization failed: {code.strip()}"

    return f"Cloudflare rejected the authorization request (HTTP {error.code})."


def _cloudflare_error_message(data: dict[str, Any]) -> str:
    errors = data.get("errors")

    if isinstance(errors, list):
        for error in errors:
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return f"Cloudflare could not create the group: {error['message']}"

    return "Cloudflare could not create the group."


def _multipart_body(boundary: str, *, metadata: bytes, module: bytes) -> bytes:
    delimiter = f"--{boundary}\r\n".encode("ascii")
    closing = f"--{boundary}--\r\n".encode("ascii")
    return b"".join(
        [
            delimiter,
            b'Content-Disposition: form-data; name="metadata"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            metadata,
            b"\r\n",
            delimiter,
            b'Content-Disposition: form-data; name="index.js"; filename="index.js"\r\n',
            b"Content-Type: application/javascript+module\r\n\r\n",
            module,
            b"\r\n",
            closing,
        ]
    )
