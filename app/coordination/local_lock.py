from __future__ import annotations

import hashlib
import os
from pathlib import Path
import threading
from types import TracebackType

from app.core.config import AppConfig


class ProjectOperationInProgressError(RuntimeError):
    pass


class ProjectOperationLock:
    """Cross-process lock for destructive local project operations."""

    _process_guard = threading.Lock()
    _held_paths: set[Path] = set()

    def __init__(self, project_uuid: str, operation: str) -> None:
        digest = hashlib.sha256(project_uuid.encode("utf-8")).hexdigest()
        self.path = AppConfig.get_locks_directory() / f"{digest}.lock"
        self.operation = operation
        self._file = None

    def __enter__(self) -> "ProjectOperationLock":
        with self._process_guard:
            if self.path in self._held_paths:
                self._raise_in_progress()

            self._held_paths.add(self.path)

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("a+b")

            if self.path.stat().st_size == 0:
                self._file.write(b"0")
                self._file.flush()

            self._file.seek(0)
            self._lock_file()
        except BaseException:
            self._close_file()

            with self._process_guard:
                self._held_paths.discard(self.path)

            raise

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._unlock_file()
        finally:
            self._close_file()

            with self._process_guard:
                self._held_paths.discard(self.path)

    def _lock_file(self) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._raise_in_progress(error)

    def _unlock_file(self) -> None:
        if self._file is None:
            return

        self._file.seek(0)

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)

    def _close_file(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _raise_in_progress(self, cause: OSError | None = None) -> None:
        error = ProjectOperationInProgressError(
            "Another Save Shift process is already modifying this project. "
            f"Wait for that operation to finish before {self.operation}."
        )

        if cause is not None:
            raise error from cause

        raise error
