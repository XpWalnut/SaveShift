from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from app.coordination.errors import CoordinationUnavailableError
from app.coordination.cloudflare_provisioning import (
    CloudflareAccount,
    CloudflareApiClient,
    CloudflareGroupCreator,
    CloudflareOAuthClient,
    CloudflareOAuthConfig,
    CloudflareProviderProvisioner,
    CloudflareProvisioningError,
    CloudflareWorkerRemover,
    OAuthTokens,
    ProvisionedProvider,
    _oauth_callback_page,
)
from app.coordination.models import PairedDevice


class _Response:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self.body = json.dumps(data or {}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def read(self) -> bytes:
        return self.body


def test_oauth_authorization_uses_pkce_and_exchanges_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    token_requests = []

    class FakeCallback:
        def __init__(self, **_kwargs) -> None:
            pass

        def wait_for_code(self, open_authorization) -> str:
            assert open_authorization() is True
            return "authorization-code"

    def fake_urlopen(request, timeout: float):
        token_requests.append(request)
        return _Response({"access_token": "cloudflare-access-token"})

    monkeypatch.setattr(
        "app.coordination.cloudflare_provisioning._OAuthCallbackReceiver",
        FakeCallback,
    )
    client = CloudflareOAuthClient(
        CloudflareOAuthConfig(
            client_id="client-123",
            scopes=("workers.write",),
        ),
        browser_open=lambda url: opened_urls.append(url) is None or True,
        urlopen_function=fake_urlopen,
    )

    tokens = client.authorize()

    parameters = parse_qs(urlparse(opened_urls[0]).query)
    assert parameters["client_id"] == ["client-123"]
    assert parameters["code_challenge_method"] == ["S256"]
    assert parameters["scope"] == ["workers.write"]
    assert "code_challenge" in parameters
    token_body = parse_qs(token_requests[0].data.decode("ascii"))
    assert token_body["code"] == ["authorization-code"]
    assert token_body["code_verifier"]
    assert token_requests[0].get_header("User-agent").startswith("SaveShift/")
    assert "OAuth-PKCE" in token_requests[0].get_header("User-agent")
    assert tokens.access_token == "cloudflare-access-token"


def test_oauth_requires_registered_public_client() -> None:
    client = CloudflareOAuthClient(CloudflareOAuthConfig(client_id=""))

    with pytest.raises(CloudflareProvisioningError, match="not configured"):
        client.authorize()


def test_oauth_callback_page_is_styled_and_escapes_content() -> None:
    page = _oauth_callback_page(
        "Group <removed>",
        "Return to Save Shift & close this tab.",
        successful=True,
    ).decode("utf-8")

    assert 'class="status success"' in page
    assert "Group &lt;removed&gt;" in page
    assert "Save Shift &amp; close" in page
    assert "Group <removed>" not in page


def test_oauth_token_error_surfaces_cloudflare_description() -> None:
    body = json.dumps(
        {
            "error": "invalid_grant",
            "error_description": "The authorization code is invalid.",
        }
    ).encode("utf-8")

    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError(
            url=CloudflareOAuthConfig.TOKEN_ENDPOINT,
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(body),
        )

    client = CloudflareOAuthClient(
        CloudflareOAuthConfig(client_id="client-123"),
        urlopen_function=fake_urlopen,
    )

    with pytest.raises(
        CloudflareProvisioningError,
        match="The authorization code is invalid",
    ):
        client._exchange_code("authorization-code", "pkce-verifier")


def test_embedded_oauth_configuration_requests_minimum_provider_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAVESHIFT_CLOUDFLARE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("SAVESHIFT_CLOUDFLARE_OAUTH_SCOPES", raising=False)

    config = CloudflareOAuthConfig.from_environment()

    assert config.client_id == "31d534da75529944866a0f849e3e31b7"
    assert config.scopes == (
        "memberships.read",
        "workers-scripts.write",
    )


def test_cloudflare_api_uploads_worker_with_scoped_bindings() -> None:
    requests = []

    def fake_urlopen(request, timeout: float):
        requests.append(request)
        return _Response({"success": True, "result": {}})

    client = CloudflareApiClient(
        "access-token",
        urlopen_function=fake_urlopen,
    )

    client.upload_worker(
        "a" * 32,
        "saveshift-coordination-123",
        b"export default {};",
        "bootstrap-secret",
        "group-123",
    )

    request = requests[0]
    assert request.method == "PUT"
    assert request.get_header("Authorization") == "Bearer access-token"
    assert b'"type":"durable_object_namespace"' in request.data
    assert b'"new_sqlite_classes":["CoordinationGroup"]' in request.data
    assert b'"type":"secret_text"' in request.data
    assert b"bootstrap-secret" in request.data
    assert b'"name":"GROUP_ID"' in request.data
    assert b'"text":"group-123"' in request.data
    assert b"export default {};" in request.data


def test_cloudflare_api_discovers_authorized_account_through_membership() -> None:
    requests = []

    def fake_urlopen(request, timeout: float):
        requests.append(request)
        return _Response(
            {
                "success": True,
                "result": [
                    {
                        "status": "accepted",
                        "account": {
                            "id": "a" * 32,
                            "name": "Alice's Account",
                        },
                    }
                ],
            }
        )

    client = CloudflareApiClient(
        "access-token",
        urlopen_function=fake_urlopen,
    )

    accounts = client.list_accounts()

    assert accounts == [CloudflareAccount("a" * 32, "Alice's Account")]
    assert requests[0].full_url.endswith(
        "/memberships?status=accepted&per_page=50"
    )


def test_cloudflare_api_surfaces_provider_error() -> None:
    body = json.dumps(
        {"success": False, "errors": [{"message": "permission denied"}]}
    ).encode("utf-8")

    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError(
            url="https://api.cloudflare.com",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(body),
        )

    client = CloudflareApiClient(
        "access-token",
        urlopen_function=fake_urlopen,
    )

    with pytest.raises(CloudflareProvisioningError, match="permission denied"):
        client.list_accounts()


def test_cloudflare_api_deletes_worker_with_force_cleanup() -> None:
    requests = []

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self) -> bytes:
            return b""

    def fake_urlopen(request, timeout: float):
        requests.append(request)
        return EmptyResponse()

    client = CloudflareApiClient(
        "temporary-token",
        urlopen_function=fake_urlopen,
    )

    client.delete_worker("account-123", "saveshift-coordination-123")

    assert requests[0].method == "DELETE"
    assert requests[0].full_url.endswith(
        "/accounts/account-123/workers/scripts/"
        "saveshift-coordination-123?force=true"
    )


def test_provider_provisioner_creates_subdomain_and_uploads_bundle(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "index.js"
    module_path.write_bytes(b"worker-module")

    class FakeApi:
        def __init__(self) -> None:
            self.upload = None
            self.enabled = None

        def get_workers_subdomain(self, account_id: str):
            return None

        def create_workers_subdomain(self, account_id: str, subdomain: str):
            assert account_id == "account-123"
            assert subdomain.startswith("saveshift-")
            return "generated-name"

        def upload_worker(
            self,
            account_id,
            script_name,
            module,
            bootstrap_token,
            group_id,
        ):
            self.upload = (
                account_id,
                script_name,
                module,
                bootstrap_token,
                group_id,
            )

        def enable_worker_subdomain(self, account_id, script_name):
            self.enabled = (account_id, script_name)

    api = FakeApi()
    provisioned = CloudflareProviderProvisioner(
        api,
        worker_module_path=module_path,
        health_check=lambda _url: True,
        sleep=lambda _seconds: None,
    ).provision("account-123")

    assert provisioned.provider_url.endswith(".generated-name.workers.dev")
    assert api.upload[0] == "account-123"
    assert api.upload[2] == b"worker-module"
    assert len(api.upload[4]) == 32
    assert api.upload[4] != "default"
    assert api.enabled == ("account-123", provisioned.script_name)
    assert provisioned.bootstrap_token


def test_provider_provisioner_reports_deployed_provider_that_never_becomes_ready(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "index.js"
    module_path.write_bytes(b"worker-module")
    health_checks: list[str] = []
    sleeps: list[float] = []

    class FakeApi:
        def get_workers_subdomain(self, _account_id: str):
            return "existing-subdomain"

        def upload_worker(self, *_args):
            return None

        def enable_worker_subdomain(self, *_args):
            return None

    provisioner = CloudflareProviderProvisioner(
        FakeApi(),
        worker_module_path=module_path,
        health_check=lambda url: health_checks.append(url) is None and False,
        sleep=sleeps.append,
    )

    with pytest.raises(CloudflareProvisioningError, match="did not become ready"):
        provisioner.provision("account-123")

    assert len(health_checks) == 5
    assert sleeps == [0.5, 0.5, 0.5, 0.5]


def test_group_creator_revokes_oauth_access_after_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []

    class FakeOAuth:
        def authorize(self):
            return OAuthTokens("temporary-token", "temporary-refresh-token")

        def revoke(self, token: str):
            events.append(("revoke", token))

    class FakeApi:
        def __init__(self, token: str) -> None:
            assert token == "temporary-token"

        def list_accounts(self):
            return [CloudflareAccount("account-123", "Save Shift")]

    class FakeProvisioner:
        def __init__(self, api) -> None:
            pass

        def provision(self, account_id: str):
            return ProvisionedProvider(
                provider_url="https://group.workers.dev",
                account_id=account_id,
                script_name="saveshift-coordination",
                bootstrap_token="bootstrap-token",
            )

    class FakeProvider:
        def __init__(self, url: str) -> None:
            assert url == "https://group.workers.dev"

        def bootstrap(self, token: str, device_name: str):
            assert (token, device_name) == ("bootstrap-token", "Gaming PC")
            return PairedDevice("device-123", "device-token", True)

    monkeypatch.setattr(
        "app.coordination.cloudflare_provisioning.HttpCoordinationProvider",
        FakeProvider,
    )
    creator = CloudflareGroupCreator(
        FakeOAuth(),
        api_factory=FakeApi,
        provisioner_factory=FakeProvisioner,
    )

    created = creator.create_group("Gaming PC")

    assert created.device.administrator is True
    assert events == [
        ("revoke", "temporary-token"),
        ("revoke", "temporary-refresh-token"),
    ]


def test_group_creator_retries_transient_bootstrap_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[str, str]] = []
    sleeps: list[float] = []

    class FakeOAuth:
        def authorize(self):
            return OAuthTokens("temporary-token")

        def revoke(self, _token: str):
            return None

    class FakeApi:
        def __init__(self, _token: str) -> None:
            pass

        def list_accounts(self):
            return [CloudflareAccount("account-123", "Save Shift")]

    class FakeProvisioner:
        def __init__(self, _api) -> None:
            pass

        def provision(self, account_id: str):
            return ProvisionedProvider(
                provider_url="https://group.workers.dev",
                account_id=account_id,
                script_name="saveshift-coordination",
                bootstrap_token="bootstrap-token",
            )

    class FakeProvider:
        def __init__(self, _url: str) -> None:
            pass

        def bootstrap(self, token: str, device_name: str):
            attempts.append((token, device_name))
            if len(attempts) < 3:
                raise CoordinationUnavailableError(
                    "The coordination provider returned HTTP 404."
                )
            return PairedDevice("device-123", "device-token", True)

    monkeypatch.setattr(
        "app.coordination.cloudflare_provisioning.HttpCoordinationProvider",
        FakeProvider,
    )
    creator = CloudflareGroupCreator(
        FakeOAuth(),
        api_factory=FakeApi,
        provisioner_factory=FakeProvisioner,
        sleep=sleeps.append,
    )

    created = creator.create_group("Gaming PC")

    assert created.device == PairedDevice("device-123", "device-token", True)
    assert attempts == [
        ("bootstrap-token", "Gaming PC"),
        ("bootstrap-token", "Gaming PC"),
        ("bootstrap-token", "Gaming PC"),
    ]
    assert sleeps == [0.5, 1.0]


def test_worker_remover_requires_and_deletes_from_authorized_account() -> None:
    events: list[tuple[str, str, str]] = []

    class FakeOAuth:
        def authorize(self, **kwargs):
            assert kwargs == {
                "completion_heading": "Group removal authorized",
                "completion_message": (
                    "Save Shift is finishing group removal. You may close this tab "
                    "and return to the app."
                ),
            }
            return OAuthTokens("temporary-token", "refresh-token")

        def revoke(self, token: str):
            events.append(("revoke", token, ""))

    class FakeApi:
        def __init__(self, token: str) -> None:
            assert token == "temporary-token"

        def list_accounts(self):
            return [CloudflareAccount("account-123", "Save Shift")]

        def delete_worker(self, account_id: str, script_name: str):
            events.append(("delete", account_id, script_name))

    remover = CloudflareWorkerRemover(FakeOAuth(), api_factory=FakeApi)

    remover.remove("account-123", "saveshift-coordination-123")

    assert events == [
        ("delete", "account-123", "saveshift-coordination-123"),
        ("revoke", "temporary-token", ""),
        ("revoke", "refresh-token", ""),
    ]
