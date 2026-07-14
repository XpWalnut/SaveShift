import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


# These must be set before importing anything that uses Save Shift's database
# or Qt. This guarantees tests never connect to the user's real database.
_test_root = Path(tempfile.mkdtemp(prefix="saveshift-tests-"))
_test_database_path = _test_root / "saveshift-test.sqlite3"
_test_settings_path = _test_root / "settings.json"
_test_locks_path = _test_root / "locks"

os.environ["SAVESHIFT_DATABASE_PATH"] = str(_test_database_path)
os.environ["SAVESHIFT_SETTINGS_PATH"] = str(_test_settings_path)
os.environ["SAVESHIFT_LOCKS_PATH"] = str(_test_locks_path)
os.environ["SAVESHIFT_DISABLE_UPDATE_CHECKS"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from app.database.database import Base, database_path, engine, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database() -> Generator[None, None, None]:
    """
    Create one isolated SQLite database for the test session.
    """
    configured_database_path = Path(database_path).resolve()
    expected_database_path = _test_database_path.resolve()

    if configured_database_path != expected_database_path:
        raise RuntimeError(
            "Refusing to run tests against a non-test database. "
            f"Expected {expected_database_path}, got {configured_database_path}."
        )

    init_db()

    yield

    engine.dispose()
    shutil.rmtree(_test_root, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    """
    Give every test empty tables while keeping the same test database file.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _test_settings_path.unlink(missing_ok=True)

    yield

    Base.metadata.drop_all(bind=engine)
    _test_settings_path.unlink(missing_ok=True)


@pytest.fixture
def temp_save_root(tmp_path: Path) -> Path:
    """
    A disposable root folder for fake game saves.
    """
    save_root = tmp_path / "game-saves"
    save_root.mkdir()

    return save_root
