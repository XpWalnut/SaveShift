from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.updates.models import UpdateRelease
from app.updates.service import UpdateService


class UpdateCheckSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class UpdateDownloadSignals(QObject):
    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str)


class UpdateCheckTask(QRunnable):
    def __init__(self, signals: UpdateCheckSignals) -> None:
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        try:
            self.signals.completed.emit(UpdateService.check_for_update())
        except Exception as error:
            self.signals.failed.emit(str(error))


class UpdateDownloadTask(QRunnable):
    def __init__(
        self,
        release: UpdateRelease,
        signals: UpdateDownloadSignals,
    ) -> None:
        super().__init__()
        self.release = release
        self.signals = signals

    def run(self) -> None:
        try:
            installer_path = UpdateService.download_installer(
                self.release,
                progress_callback=self.signals.progress.emit,
            )
            self.signals.completed.emit(installer_path)
        except Exception as error:
            self.signals.failed.emit(str(error))


class UpdateController(QObject):
    update_available = Signal(object, bool)
    no_update_available = Signal(bool)
    check_failed = Signal(str, bool)
    download_progress = Signal(int)
    download_completed = Signal(object)
    download_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._check_running = False
        self._download_running = False
        self._check_task: UpdateCheckTask | None = None
        self._download_task: UpdateDownloadTask | None = None

    def check_for_updates(self, *, manual: bool) -> bool:
        if self._check_running:
            return False

        self._check_running = True
        signals = UpdateCheckSignals(self)
        task = UpdateCheckTask(signals)
        self._check_task = task
        signals.completed.connect(
            lambda release: self._handle_check_completed(release, manual)
        )
        signals.failed.connect(
            lambda message: self._handle_check_failed(message, manual)
        )
        self._thread_pool.start(task)
        return True

    def download_update(self, release: UpdateRelease) -> bool:
        if self._download_running:
            return False

        self._download_running = True
        signals = UpdateDownloadSignals(self)
        task = UpdateDownloadTask(release, signals)
        self._download_task = task
        signals.progress.connect(self.download_progress.emit)
        signals.completed.connect(self._handle_download_completed)
        signals.failed.connect(self._handle_download_failed)
        self._thread_pool.start(task)
        return True

    def _handle_check_completed(
        self,
        release: UpdateRelease | None,
        manual: bool,
    ) -> None:
        self._check_running = False
        self._check_task = None

        if release is None:
            self.no_update_available.emit(manual)
            return

        self.update_available.emit(release, manual)

    def _handle_check_failed(self, message: str, manual: bool) -> None:
        self._check_running = False
        self._check_task = None
        self.check_failed.emit(message, manual)

    def _handle_download_completed(self, installer_path: object) -> None:
        self._download_running = False
        self._download_task = None
        self.download_completed.emit(installer_path)

    def _handle_download_failed(self, message: str) -> None:
        self._download_running = False
        self._download_task = None
        self.download_failed.emit(message)
