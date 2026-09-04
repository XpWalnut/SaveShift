import logging
import re

import pytest

from app.core.logging import diagnostic_operation


def test_operation_records_timing_and_matching_id(caplog):
    with caplog.at_level(logging.INFO, logger="SaveShift"):
        with diagnostic_operation("test.operation"):
            pass
    assert "started" in caplog.text
    assert "completed elapsed=" in caplog.text
    ids = re.findall(r"id=([a-f0-9]+)", caplog.text)
    assert len(ids) == 2 and ids[0] == ids[1]


def test_failure_preserves_exception_without_logging_secrets(caplog):
    secret = "invite-token-and-private-save-name"
    error = ValueError(secret)
    with caplog.at_level(logging.INFO, logger="SaveShift"):
        with pytest.raises(ValueError) as caught:
            with diagnostic_operation("test.failure"):
                raise error
    assert caught.value is error
    assert "error_type=ValueError" in caplog.text
    assert "stack=" in caplog.text
    assert "completed" not in caplog.text
    assert secret not in caplog.text


def test_decorated_calls_have_distinct_ids(caplog):
    @diagnostic_operation("test.decorated")
    def operation(value):
        return value

    with caplog.at_level(logging.INFO, logger="SaveShift"):
        assert operation(1) == 1
        assert operation(2) == 2
    ids = re.findall(r"id=([a-f0-9]+)", caplog.text)
    assert ids[0] == ids[1]
    assert ids[2] == ids[3]
    assert ids[0] != ids[2]
