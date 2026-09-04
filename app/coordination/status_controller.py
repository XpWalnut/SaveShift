from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.coordination.models import LockLease
from app.coordination.provider import CoordinationProvider


class LockStatusSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class LockStatusTask(QRunnable):
    def __init__(
        self,
        provider: CoordinationProvider,
        project_uuids: list[str],
        signals: LockStatusSignals,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.project_uuids = project_uuids
        self.signals = signals

    def run(self) -> None:
        try:
            statuses: dict[str, LockLease | None] = {
                project_uuid: self.provider.get_lock(project_uuid)
                for project_uuid in self.project_uuids
            }
        except Exception as error:
            self.signals.failed.emit(str(error))
            return

        self.signals.completed.emit(statuses)


class LockStatusController(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._refresh_running = False
        self._task: LockStatusTask | None = None

    def refresh(
        self,
        provider: CoordinationProvider,
        project_uuids: list[str],
    ) -> bool:
        if self._refresh_running or not project_uuids:
            return False

        self._refresh_running = True
        signals = LockStatusSignals(self)
        task = LockStatusTask(provider, project_uuids, signals)
        self._task = task
        signals.completed.connect(self._handle_completed)
        signals.failed.connect(self._handle_failed)
        self._thread_pool.start(task)
        return True

    def _handle_completed(
        self,
        statuses: dict[str, LockLease | None],
    ) -> None:
        self._refresh_running = False
        self._task = None
        self.completed.emit(statuses)

    def _handle_failed(self, message: str) -> None:
        self._refresh_running = False
        self._task = None
        self.failed.emit(message)
