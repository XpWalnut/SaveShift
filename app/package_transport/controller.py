from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.coordination.models import LockLease
from app.coordination.provider import PackageCatalogProvider, PackageKeyProvider
from app.services.group_handoff_service import GroupHandoffService


class PackageHandoffSignals(QObject):
    publish_completed = Signal(object)
    download_completed = Signal(object)
    legal_agreement_required = Signal(str)
    failed = Signal(str)


class PublishPackageTask(QRunnable):
    def __init__(
        self,
        package_path: Path,
        lease: LockLease,
        provider: PackageCatalogProvider | PackageKeyProvider,
        signals: PackageHandoffSignals,
    ) -> None:
        super().__init__()
        self.package_path = package_path
        self.lease = lease
        self.provider = provider
        self.signals = signals

    def run(self) -> None:
        try:
            result = GroupHandoffService.publish_package(
                self.package_path,
                self.lease,
                self.provider,
                legal_agreement_handler=(
                    self.signals.legal_agreement_required.emit
                ),
            )
            self.signals.publish_completed.emit(result)
        except Exception as error:
            self.signals.failed.emit(str(error))


class DownloadPackageTask(QRunnable):
    def __init__(
        self,
        project_uuid: str,
        provider: PackageCatalogProvider | PackageKeyProvider,
        signals: PackageHandoffSignals,
    ) -> None:
        super().__init__()
        self.project_uuid = project_uuid
        self.provider = provider
        self.signals = signals

    def run(self) -> None:
        try:
            result = GroupHandoffService.download_latest(
                self.project_uuid,
                self.provider,
            )
            self.signals.download_completed.emit(result)
        except Exception as error:
            self.signals.failed.emit(str(error))


class PackageHandoffController(QObject):
    publish_completed = Signal(object)
    download_completed = Signal(object)
    legal_agreement_required = Signal(str)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._running = False
        self._task: QRunnable | None = None

    @property
    def running(self) -> bool:
        return self._running

    def publish(
        self,
        package_path: Path,
        lease: LockLease,
        provider: PackageCatalogProvider | PackageKeyProvider,
    ) -> bool:
        if self._running:
            return False

        self._running = True
        signals = PackageHandoffSignals(self)
        task = PublishPackageTask(package_path, lease, provider, signals)
        self._task = task
        signals.publish_completed.connect(self._publish_finished)
        signals.legal_agreement_required.connect(
            self.legal_agreement_required.emit
        )
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def download_latest(
        self,
        project_uuid: str,
        provider: PackageCatalogProvider | PackageKeyProvider,
    ) -> bool:
        if self._running:
            return False

        self._running = True
        signals = PackageHandoffSignals(self)
        task = DownloadPackageTask(project_uuid, provider, signals)
        self._task = task
        signals.download_completed.connect(self._download_finished)
        signals.failed.connect(self._failed)
        self._thread_pool.start(task)
        return True

    def _publish_finished(self, result: object) -> None:
        self._finish()
        self.publish_completed.emit(result)

    def _download_finished(self, result: object) -> None:
        self._finish()
        self.download_completed.emit(result)

    def _failed(self, message: str) -> None:
        self._finish()
        self.failed.emit(message)

    def _finish(self) -> None:
        self._running = False
        self._task = None
