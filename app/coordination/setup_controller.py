from collections.abc import Callable
from dataclasses import dataclass

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


class GroupSetupSignals(QObject):
    create_completed = Signal(object)
    join_completed = Signal(object, object)
    leave_completed = Signal(object)
    failed = Signal(str)


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

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        creator_factory: Callable[[], CloudflareGroupCreator] | None = None,
        remover_factory: Callable[[], CloudflareWorkerRemover] | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._running = False
        self._task: QRunnable | None = None
        self._creator_factory = creator_factory or self._default_creator
        self._remover_factory = remover_factory or self._default_remover

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
