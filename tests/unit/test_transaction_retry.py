import pytest

from backend.app.db.repository import run_with_serialization_retry


class SqlStateError(RuntimeError):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def test_retry_replays_complete_operation_after_40001() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SqlStateError("40001")
        return "committed"

    result = run_with_serialization_retry(operation, sleeper=sleeps.append)

    assert result == "committed"
    assert attempts == 2
    assert len(sleeps) == 1


def test_retry_is_bounded_for_repeated_40001() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise SqlStateError("40001")

    with pytest.raises(SqlStateError):
        run_with_serialization_retry(operation, max_attempts=3, sleeper=lambda _: None)

    assert attempts == 3


def test_retry_does_not_repeat_non_serialization_errors() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise SqlStateError("23505")

    with pytest.raises(SqlStateError):
        run_with_serialization_retry(operation, max_attempts=3, sleeper=lambda _: None)

    assert attempts == 1


def test_retry_reuses_preallocated_business_identity() -> None:
    command = object()
    seen: list[object] = []

    def operation() -> object:
        seen.append(command)
        if len(seen) < 3:
            raise SqlStateError("40001")
        return command

    result = run_with_serialization_retry(operation, sleeper=lambda _: None)

    assert result is command
    assert all(item is command for item in seen)
