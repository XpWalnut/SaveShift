from pathlib import Path
import subprocess
import sys
import time

import pytest

from app.coordination.local_lock import (
    ProjectOperationInProgressError,
    ProjectOperationLock,
)


def test_project_operation_lock_rejects_concurrent_local_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAVESHIFT_LOCKS_PATH", str(tmp_path / "locks"))

    with ProjectOperationLock("project-uuid", "importing into it"):
        with pytest.raises(
            ProjectOperationInProgressError,
            match="already modifying this project",
        ):
            with ProjectOperationLock("project-uuid", "restoring it"):
                pass


def test_project_operation_lock_can_be_reacquired_after_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAVESHIFT_LOCKS_PATH", str(tmp_path / "locks"))

    with ProjectOperationLock("project-uuid", "hosting it"):
        pass

    with ProjectOperationLock("project-uuid", "hosting it"):
        pass

    assert len(list((tmp_path / "locks").glob("*.lock"))) == 1


def test_different_projects_do_not_block_each_other(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAVESHIFT_LOCKS_PATH", str(tmp_path / "locks"))

    with ProjectOperationLock("project-one", "hosting it"):
        with ProjectOperationLock("project-two", "hosting it"):
            pass


def test_project_operation_lock_blocks_another_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks_path = tmp_path / "locks"
    ready_path = tmp_path / "ready"
    release_path = tmp_path / "release"
    monkeypatch.setenv("SAVESHIFT_LOCKS_PATH", str(locks_path))
    child_script = "\n".join(
        [
            "import os, pathlib, sys, time",
            "os.environ['SAVESHIFT_LOCKS_PATH'] = sys.argv[1]",
            "from app.coordination.local_lock import ProjectOperationLock",
            "with ProjectOperationLock('project-uuid', 'hosting it'):",
            "    pathlib.Path(sys.argv[2]).touch()",
            "    while not pathlib.Path(sys.argv[3]).exists():",
            "        time.sleep(0.01)",
        ]
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_script,
            str(locks_path),
            str(ready_path),
            str(release_path),
        ],
    )

    try:
        deadline = time.monotonic() + 5

        while not ready_path.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"lock-holder process exited with {process.returncode}")

            time.sleep(0.01)

        assert ready_path.exists(), "lock-holder process did not become ready"

        with pytest.raises(ProjectOperationInProgressError):
            with ProjectOperationLock("project-uuid", "restoring it"):
                pass
    finally:
        release_path.touch()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == 0
