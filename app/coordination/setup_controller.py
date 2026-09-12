from collections.abc import Callable
from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.coordination.cloudflare_provisioning import (
    CloudflareGroupCreator,
    CloudflareOAuthClient,
    CloudflareOAuthConfig,
    CloudflareWorkerRemover,
    CreatedGroup,
)
from app.coordination.http_provider import HttpCoordinationProvider
from app.coordination.models import GroupInvitation, PairedDevice
from app.core.logging import diagnostic_operation
from app.steam.native_group_service import (
    CreatedSteamGroup,
    SteamNativeGroupService,
)
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_invitation import (
    JoinedSteamGroup,
    SteamGroupInvitationService,
)
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.native_ugc_client import SteamworksUgcClient
from app.steam.social_client import SteamLobbyJoinRequest, SteamLobbyMessage


class GroupSetupSignals(QObject):
    create_completed = Signal(object)
    join_completed = Signal(object, object)
    leave_completed = Signal(object)
    failed = Signal(str)
    steam_create_completed = Signal(object)
    steam_invitation_ready = Signal(str)
    steam_member_admitted = Signal(object)
    steam_join_waiting = Signal()
    steam_join_completed = Signal(object)


@dataclass(frozen=True)
class GroupLeaveOutcome:
    group_empty: bool
    cloudflare_worker_removed: bool = False
    cleanup_warning: str = ""


class CreateGroupTask(QRunnable):
    def __init__(
        self,
        device_name: str,
        signals: GroupSetupSignals,
        creator_factory: Callable[[], CloudflareGroupCreator],
    ) -> None:
        super().__init__()
        self.device_name = device_name
        self.signals = signals
        self.creator_factory = creator_factory

    def run(self) -> None:
        try:
            with diagnostic_operation("group.create"):
                created = self.creator_factory().create_group(self.device_name)
            self.signals.create_completed.emit(created)
        except Exception as error:
            self.signals.failed.emit(str(error))


class CreateSteamGroupTask(QRunnable):
    def __init__(
        self,
        group_name: str,
        signals: GroupSetupSignals,
        service_factory: Callable[[], SteamNativeGroupService],
    ) -> None:
        super().__init__()
        self.group_name = group_name
        self.signals = signals
        self.service_factory = service_factory

    def run(self) -> None:
        try:
            with diagnostic_operation("steam_group.create"):
                created = self.service_factory().create_group(self.group_name)
            self.signals.steam_create_completed.emit(created)
        except Exception as error:
            self.signals.failed.emit(str(error))


class InviteSteamMemberTask(QRunnable):
    def __init__(
        self,
        manifest_item_id: str,
        group_id: str,
        signals: GroupSetupSignals,
        client_factory: Callable[[], SteamworksUgcClient],
        identity_store_factory: Callable[[], SteamDeviceIdentityStore],
        timeout_seconds: float,
    ) -> None:
        super().__init__()
        self.manifest_item_id = manifest_item_id
        self.group_id = group_id
        self.signals = signals
        self.client_factory = client_factory
        self.identity_store_factory = identity_store_factory
        self.timeout_seconds = timeout_seconds

    def run(self) -> None:
        client: SteamworksUgcClient | None = None
        lobby_id = ""
        try:
            client = self.client_factory()
            steam_identity = client.current_identity()
            identity = self.identity_store_factory().load_or_create(
                steam_identity.steam_id
            )
            transport = SteamGroupManifestTransport(client)
            manifest = transport.download(self.manifest_item_id)
            if manifest.group_id != self.group_id:
                raise ValueError("The saved Steam group manifest does not match.")
            group_key = manifest.group_key_for(identity)
            invitation = SteamGroupInvitationService(client, transport)
            lobby = invitation.begin_invitation(manifest, self.manifest_item_id)
            lobby_id = lobby.lobby_id
            self.signals.steam_invitation_ready.emit(lobby_id)
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                for event in client.poll_social_events():
                    if not isinstance(event, SteamLobbyMessage):
                        continue
                    try:
                        updated = invitation.admit_member(
                            event,
                            self.manifest_item_id,
                            manifest,
                            group_key,
                            identity,
                        )
                    except ValueError:
                        continue
                    self.signals.steam_member_admitted.emit(updated)
                    return
                time.sleep(0.05)
            raise TimeoutError("No friend joined the Steam invitation in time.")
        except Exception as error:
            self.signals.failed.emit(str(error))
        finally:
            if client is not None:
                if lobby_id:
                    try:
                        client.leave_lobby(lobby_id)
                    except Exception:
                        pass
                client.close()


class JoinSteamGroupTask(QRunnable):
    def __init__(
        self,
        signals: GroupSetupSignals,
        client_factory: Callable[[], SteamworksUgcClient],
        identity_store_factory: Callable[[], SteamDeviceIdentityStore],
        timeout_seconds: float,
    ) -> None:
        super().__init__()
        self.signals = signals
        self.client_factory = client_factory
        self.identity_store_factory = identity_store_factory
        self.timeout_seconds = timeout_seconds

    def run(self) -> None:
        client: SteamworksUgcClient | None = None
        lobby_id = ""
        try:
            client = self.client_factory()
            steam_identity = client.current_identity()
            identity = self.identity_store_factory().load_or_create(
                steam_identity.steam_id
            )
            transport = SteamGroupManifestTransport(client)
            invitation = SteamGroupInvitationService(client, transport)
            self.signals.steam_join_waiting.emit()
            deadline = time.monotonic() + self.timeout_seconds
            membership_requested = False
            while time.monotonic() < deadline:
                for event in client.poll_social_events():
                    if isinstance(event, SteamLobbyJoinRequest):
                        client.join_lobby(event.lobby_id)
                        lobby_id = event.lobby_id
                        invitation.request_membership(lobby_id, identity)
                        membership_requested = True
                    elif (
                        membership_requested
                        and isinstance(event, SteamLobbyMessage)
                        and event.lobby_id == lobby_id
                    ):
                        try:
                            joined = invitation.complete_membership(event, identity)
                        except ValueError:
                            continue
                        self.signals.steam_join_completed.emit(joined)
                        return
                time.sleep(0.05)
            raise TimeoutError("No Steam group invitation was completed in time.")
        except Exception as error:
            self.signals.failed.emit(str(error))
        finally:
            if client is not None:
                if lobby_id:
                    try:
                        client.leave_lobby(lobby_id)
                    except Exception:
                        pass
                client.close()


class JoinGroupTask(QRunnable):
    def __init__(
        self,
        invitation: GroupInvitation,
        device_name: str,
        signals: GroupSetupSignals,
    ) -> None:
        super().__init__()
        self.invitation = invitation
        self.device_name = device_name
        self.signals = signals

    def run(self) -> None:
        try:
            provider = HttpCoordinationProvider(self.invitation.provider_url)
            with diagnostic_operation("group.join"):
                device = provider.join(
                    self.invitation.invitation_token,
                    self.device_name,
                )
            self.signals.join_completed.emit(self.invitation, device)
        except Exception as error:
            self.signals.failed.emit(str(error))


class LeaveGroupTask(QRunnable):
    def __init__(
        self,
        provider_url: str,
        device_token: str,
        account_id: str,
        script_name: str,
        signals: GroupSetupSignals,
        remover_factory: Callable[[], CloudflareWorkerRemover],
    ) -> None:
        super().__init__()
        self.provider_url = provider_url
        self.device_token = device_token
        self.account_id = account_id
        self.script_name = script_name
        self.signals = signals
        self.remover_factory = remover_factory

    def run(self) -> None:
        try:
            provider = HttpCoordinationProvider(
                self.provider_url,
                device_token=self.device_token,
            )
            with diagnostic_operation("group.leave"):
                result = provider.leave_group()
        except Exception as error:
            self.signals.failed.emit(str(error))
            return

        removed = False
        cleanup_warning = ""

        if result.group_empty and self.account_id and self.script_name:
            try:
                with diagnostic_operation("group.cleanup"):
                    self.remover_factory().remove(self.account_id, self.script_name)
                removed = True
            except Exception as error:
                cleanup_warning = str(error)

        self.signals.leave_completed.emit(
            GroupLeaveOutcome(
                group_empty=result.group_empty,
                cloudflare_worker_removed=removed,
                cleanup_warning=cleanup_warning,
            )
        )


class GroupSetupController(QObject):
    create_completed = Signal(object)
    join_completed = Signal(object, object)
    leave_completed = Signal(object)
    failed = Signal(str)
    steam_create_completed = Signal(object)
    steam_invitation_ready = Signal(str)
    steam_member_admitted = Signal(object)
    steam_join_waiting = Signal()
    steam_join_completed = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        creator_factory: Callable[[], CloudflareGroupCreator] | None = None,
        remover_factory: Callable[[], CloudflareWorkerRemover] | None = None,
        steam_service_factory: Callable[[], SteamNativeGroupService] | None = None,
        steam_client_factory: Callable[[], SteamworksUgcClient] | None = None,
        identity_store_factory: Callable[[], SteamDeviceIdentityStore] | None = None,
        steam_invitation_timeout_seconds: float = 120.0,
    ) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._running = False
        self._task: QRunnable | None = None
        self._creator_factory = creator_factory or self._default_creator
        self._remover_factory = remover_factory or self._default_remover
        self._steam_service_factory = (
            steam_service_factory or SteamNativeGroupService
        )
        self._steam_client_factory = steam_client_factory or SteamworksUgcClient
        self._identity_store_factory = (
            identity_store_factory or SteamDeviceIdentityStore
        )
        self._steam_invitation_timeout_seconds = steam_invitation_timeout_seconds

    @property
    def running(self) -> bool:
        return self._running

    def create_group(self, device_name: str) -> bool:
        if self._running:
            return False

        self._running = True
        signals = GroupSetupSignals(self)
        task = CreateGroupTask(
            device_name,
            signals,
            self._creator_factory,
        )
        self._task = task
        signals.create_completed.connect(self._create_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def create_steam_group(self, group_name: str) -> bool:
        if self._running:
            return False
        self._running = True
        signals = GroupSetupSignals(self)
        task = CreateSteamGroupTask(
            group_name,
            signals,
            self._steam_service_factory,
        )
        self._task = task
        signals.steam_create_completed.connect(self._steam_create_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def invite_steam_member(self, manifest_item_id: str, group_id: str) -> bool:
        if self._running:
            return False
        self._running = True
        signals = GroupSetupSignals(self)
        task = InviteSteamMemberTask(
            manifest_item_id,
            group_id,
            signals,
            self._steam_client_factory,
            self._identity_store_factory,
            self._steam_invitation_timeout_seconds,
        )
        self._task = task
        signals.steam_invitation_ready.connect(
            self.steam_invitation_ready.emit
        )
        signals.steam_member_admitted.connect(self._steam_member_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def join_steam_group(self) -> bool:
        if self._running:
            return False
        self._running = True
        signals = GroupSetupSignals(self)
        task = JoinSteamGroupTask(
            signals,
            self._steam_client_factory,
            self._identity_store_factory,
            self._steam_invitation_timeout_seconds,
        )
        self._task = task
        signals.steam_join_waiting.connect(self.steam_join_waiting.emit)
        signals.steam_join_completed.connect(self._steam_join_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def join_group(
        self,
        invitation: GroupInvitation,
        device_name: str,
    ) -> bool:
        if self._running:
            return False

        self._running = True
        signals = GroupSetupSignals(self)
        task = JoinGroupTask(invitation, device_name, signals)
        self._task = task
        signals.join_completed.connect(self._join_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def leave_group(
        self,
        provider_url: str,
        device_token: str,
        *,
        account_id: str = "",
        script_name: str = "",
    ) -> bool:
        if self._running:
            return False

        self._running = True
        signals = GroupSetupSignals(self)
        task = LeaveGroupTask(
            provider_url,
            device_token,
            account_id,
            script_name,
            signals,
            self._remover_factory,
        )
        self._task = task
        signals.leave_completed.connect(self._leave_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def _create_finished(self, created: CreatedGroup) -> None:
        self._finish()
        self.create_completed.emit(created)

    def _steam_create_finished(self, created: CreatedSteamGroup) -> None:
        self._finish()
        self.steam_create_completed.emit(created)

    def _steam_member_finished(self, manifest: object) -> None:
        self._finish()
        self.steam_member_admitted.emit(manifest)

    def _steam_join_finished(self, joined: JoinedSteamGroup) -> None:
        self._finish()
        self.steam_join_completed.emit(joined)

    def _join_finished(
        self,
        invitation: GroupInvitation,
        device: PairedDevice,
    ) -> None:
        self._finish()
        self.join_completed.emit(invitation, device)

    def _leave_finished(self, outcome: GroupLeaveOutcome) -> None:
        self._finish()
        self.leave_completed.emit(outcome)

    def _failed(self, message: str) -> None:
        self._finish()
        self.failed.emit(message)

    def _finish(self) -> None:
        self._running = False
        self._task = None

    @staticmethod
    def _default_creator() -> CloudflareGroupCreator:
        config = CloudflareOAuthConfig.from_environment()
        return CloudflareGroupCreator(CloudflareOAuthClient(config))

    @staticmethod
    def _default_remover() -> CloudflareWorkerRemover:
        config = CloudflareOAuthConfig.from_environment()
        return CloudflareWorkerRemover(CloudflareOAuthClient(config))
