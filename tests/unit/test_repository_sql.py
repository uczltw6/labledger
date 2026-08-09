from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from backend.app.db.psycopg_repository import PsycopgStructuredMemoryRepository
from backend.app.db.types import ExperimentRunRecord


class RecordingConnection:
    def __init__(self) -> None:
        self.query = ""
        self.parameters: tuple[object, ...] = ()

    def execute(self, query: str, parameters: tuple[object, ...]):  # type: ignore[no-untyped-def]
        self.query = query
        self.parameters = parameters
        return self

    def fetchone(self) -> dict[str, object]:
        return {"id": uuid4()}


def test_run_insert_passes_quoted_values_as_parameters() -> None:
    connection = RecordingConnection()
    quoted_name = "operator's deterministic run"
    record = ExperimentRunRecord(
        id=uuid4(),
        name=quoted_name,
        status="running",
        recipe_version="p2-test",
        started_at=datetime.now(UTC),
        ended_at=None,
        current_step=0,
        context={"note": "quoted ' context"},
        created_by="pytest",
    )

    PsycopgStructuredMemoryRepository._insert_run(
        cast(Any, connection),
        record,
        idempotent=False,
    )

    assert "%s" in connection.query
    assert quoted_name not in connection.query
    assert quoted_name in connection.parameters
