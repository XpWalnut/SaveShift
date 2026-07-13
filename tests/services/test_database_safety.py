from pathlib import Path

import pytest

from app.database.database import _resolve_database_path


def test_explicit_test_database_path_is_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database = tmp_path / "isolated.sqlite3"
    monkeypatch.setenv("SAVESHIFT_DATABASE_PATH", str(test_database))

    assert _resolve_database_path() == str(test_database)


def test_pytest_cannot_fall_back_to_application_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAVESHIFT_DATABASE_PATH", raising=False)

    with pytest.raises(
        RuntimeError,
        match="Refusing to use the application database from pytest",
    ):
        _resolve_database_path()
