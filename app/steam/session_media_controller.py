from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.coordination.models import CatalogPackage
from app.steam.native_provider import SteamNativeCoordinationProvider


class _MediaSignals(QObject):
    completed = Signal(object)
    failed = Signal(str, str)


class _PublishMediaTask(QRunnable):
    def __init__(self, provider, package, image_path, captured_at_utc, signals):
        super().__init__()
        self.provider = provider
        self.package = package
        self.image_path = image_path
        self.captured_at_utc = captured_at_utc
        self.signals = signals

    def run(self) -> None:
        try:
            result = self.provider.publish_session_image(
                self.package,
                self.image_path,
                self.captured_at_utc,
            )
            self.signals.completed.emit((self.package, result))
        except Exception as error:
            self.signals.failed.emit("publish", str(error))


class _DownloadMediaTask(QRunnable):
    def __init__(self, provider, package, destination, signals):
        super().__init__()
        self.provider = provider
        self.package = package
        self.destination = destination
        self.signals = signals

    def run(self) -> None:
        try:
            path = self.provider.download_session_image(
                self.package,
                self.destination,
            )
            self.signals.completed.emit((self.package, path))
        except Exception as error:
            self.signals.failed.emit("download", str(error))


class _ClearMediaTask(QRunnable):
    def __init__(self, provider, project_uuid, signals):
        super().__init__()
        self.provider = provider
        self.project_uuid = project_uuid
        self.signals = signals

    def run(self) -> None:
        try:
            result = self.provider.clear_session_image(self.project_uuid)
            self.signals.completed.emit((self.project_uuid, result))
        except Exception as error:
            self.signals.failed.emit("clear", str(error))


class SessionMediaController(QObject):
    publish_completed = Signal(object)
    download_completed = Signal(object)
    clear_completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._tasks: set[QRunnable] = set()

    def publish(
        self,
        provider: SteamNativeCoordinationProvider,
        package: CatalogPackage,
        image_path: Path,
        captured_at_utc: str,
    ) -> None:
        signals = _MediaSignals(self)
        task = _PublishMediaTask(
            provider,
            package,
            image_path,
            captured_at_utc,
            signals,
        )
        self._tasks.add(task)
        signals.completed.connect(
            lambda result, current=task: self._finished(
                current, self.publish_completed, result
            )
        )
        signals.failed.connect(
            lambda operation, message, current=task: self._failed(
                current, operation, message
            )
        )
        self._thread_pool.start(task)

    def download(
        self,
        provider: SteamNativeCoordinationProvider,
        package: CatalogPackage,
        destination: Path,
    ) -> None:
        signals = _MediaSignals(self)
        task = _DownloadMediaTask(provider, package, destination, signals)
        self._tasks.add(task)
        signals.completed.connect(
            lambda result, current=task: self._finished(
                current, self.download_completed, result
            )
        )
        signals.failed.connect(
            lambda operation, message, current=task: self._failed(
                current, operation, message
            )
        )
        self._thread_pool.start(task)

    def clear(
        self,
        provider: SteamNativeCoordinationProvider,
        project_uuid: str,
    ) -> None:
        signals = _MediaSignals(self)
        task = _ClearMediaTask(provider, project_uuid, signals)
        self._tasks.add(task)
        signals.completed.connect(
            lambda result, current=task: self._finished(
                current, self.clear_completed, result
            )
        )
        signals.failed.connect(
            lambda operation, message, current=task: self._failed(
                current, operation, message
            )
        )
        self._thread_pool.start(task)

    def _finished(self, task, signal, result) -> None:
        self._tasks.discard(task)
        signal.emit(result)

    def _failed(self, task, operation: str, message: str) -> None:
        self._tasks.discard(task)
        self.failed.emit(operation, message)
