"""Verify P2 locally and, when configured, across two fresh OS processes."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.fake import FakeStructuredMemoryRepository  # noqa: E402
from backend.app.db.mapping import DEFAULT_SEED_LAB_ID, build_hero_seed, map_trace  # noqa: E402
from backend.app.db.migrations import (  # noqa: E402
    EXPECTED_P2_TABLES,
    apply_migration,
    migration_statements,
    verify_p2_schema,
)
from backend.app.db.psycopg_repository import PsycopgStructuredMemoryRepository  # noqa: E402
from backend.app.devices.scenarios import run_scenario_a  # noqa: E402

MIGRATION = ROOT / "migrations" / "001_init.sql"


def _database_url() -> str | None:
    configured = os.environ.get("COCKROACH_DATABASE_URL")
    if configured:
        return configured
    env_path = ROOT / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "COCKROACH_DATABASE_URL" and value.strip():
            return value.strip().strip('"').strip("'")
    return None


def _preflight_database_url(
    database_url: str,
    *,
    platform_name: str = os.name,
    appdata: Path | None = None,
) -> None:
    """Reject malformed or unverifiable Cloud URLs without echoing credentials."""

    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError(
            "COCKROACH_DATABASE_URL must be the complete postgresql:// connection URL"
        )
    password = unquote(parsed.password or "")
    if not parsed.username or not password:
        raise RuntimeError("COCKROACH_DATABASE_URL must include a SQL user and password")
    if any(marker in password.upper() for marker in ("ENTER-PASSWORD", "YOUR_PASSWORD")):
        raise RuntimeError("COCKROACH_DATABASE_URL still contains a password placeholder")

    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("sslmode") != ["verify-full"]:
        raise RuntimeError("CockroachDB Cloud requires sslmode=verify-full for this gate")
    if platform_name != "nt" or query.get("sslrootcert"):
        return

    roaming = appdata
    if roaming is None:
        configured = os.environ.get("APPDATA")
        roaming = Path(configured) if configured else Path.home() / "AppData" / "Roaming"
    root_certificate = roaming / "postgresql" / "root.crt"
    if not root_certificate.is_file():
        raise RuntimeError(
            "CockroachDB Cloud root CA is missing; download it to the standard "
            "Windows postgresql/root.crt path before running the live gate"
        )


def _local_checks() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    tables = set(
        re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.([a-z_]+)",
            sql,
            flags=re.IGNORECASE,
        )
    )
    if tables != EXPECTED_P2_TABLES:
        raise RuntimeError("migration does not define the exact eleven P2 tables")
    if re.search(r"\b(VECTOR|DROP|TRUNCATE|DELETE)\b", sql, flags=re.IGNORECASE):
        raise RuntimeError("migration contains P3 or destructive SQL")
    if not migration_statements(MIGRATION):
        raise RuntimeError("migration has no executable statements")

    trace = run_scenario_a()
    rows = map_trace(
        trace,
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=uuid4(),
        base_time=datetime.now(UTC),
    )
    repository = FakeStructuredMemoryRepository()
    repository.save_trace(rows)
    restored = repository.load_run_restore(rows.run.id)
    if restored is None:
        raise RuntimeError("local fake failed to restore the trace")
    if restored.run.current_step != rows.run.current_step:
        raise RuntimeError("local fake restored the wrong run step")
    if [record.sequence_no for record in restored.timeline] != list(
        range(1, rows.run.current_step + 1)
    ):
        raise RuntimeError("local fake changed the trace timeline order")
    print("[PASS] P2 local schema, mapping, and fake restore checks")
    print("[INFO] Local fake evidence does not satisfy Gate P2")


def _worker_write(database_url: str) -> int:
    trace = run_scenario_a()
    run_id = uuid4()
    rows = map_trace(
        trace,
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=run_id,
        base_time=datetime.now(UTC),
    )
    repository = PsycopgStructuredMemoryRepository(database_url)
    repository.save_hero_seed(build_hero_seed())
    repository.save_trace(rows)
    print(
        json.dumps(
            {
                "run_id": str(run_id),
                "step": rows.run.current_step,
                "actions": len(rows.actions),
                "outcomes": len(rows.outcomes),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _worker_read(
    database_url: str,
    run_id: UUID,
    expected_step: int,
    expected_actions: int,
    expected_outcomes: int,
) -> int:
    repository = PsycopgStructuredMemoryRepository(database_url)
    restored = repository.load_run_restore(run_id)
    if restored is None:
        raise RuntimeError("fresh process could not load the persisted run")
    if restored.run.current_step != expected_step or restored.checkpoint.step_no != expected_step:
        raise RuntimeError("fresh process restored the wrong checkpoint step")
    if restored.action_count != expected_actions or restored.outcome_count != expected_outcomes:
        raise RuntimeError("fresh process restored incomplete action/outcome evidence")
    if restored.run.status != "completed":
        raise RuntimeError("fresh process restored the wrong run status")
    sequence = [record.sequence_no for record in restored.timeline]
    if sequence != list(range(1, expected_step + 1)):
        raise RuntimeError("fresh process restored a non-contiguous timeline")
    if not any(
        record.event_type == "outcome_recorded" and record.detail.get("success") is False
        for record in restored.timeline
    ):
        raise RuntimeError("fresh process lost the failed action evidence")
    state = restored.checkpoint.agent_state
    if state.get("current_step") != expected_step:
        raise RuntimeError("checkpoint agent state does not match persisted progress")
    if not isinstance(state.get("device_states"), dict):
        raise RuntimeError("checkpoint lacks process-independent device state")
    if not isinstance(state.get("completed_action_ids"), list):
        raise RuntimeError("checkpoint lacks completed-action idempotency evidence")
    completed_action_ids = state["completed_action_ids"]
    if (
        restored.checkpoint.last_action_id is None
        or str(restored.checkpoint.last_action_id) not in completed_action_ids
    ):
        raise RuntimeError("checkpoint last action is not recorded as completed")
    if (
        restored.checkpoint.pending_action_id is not None
        or state.get("pending_action_id") is not None
    ):
        raise RuntimeError("completed checkpoint retained a pending action")
    device_states = state["device_states"]
    scope_state = device_states.get("scope_01")
    if not isinstance(scope_state, dict) or scope_state.get("connection_state") != "connected":
        raise RuntimeError("checkpoint did not restore the verified scope connection")
    if scope_state.get("active_faults") != []:
        raise RuntimeError("checkpoint restored a resolved scope fault")
    if not isinstance(state.get("physical_state"), dict):
        raise RuntimeError("checkpoint lacks explicit physical settings")
    print('{"restored":true}')
    return 0


def _run_worker(arguments: list[str]) -> tuple[int, int, str]:
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), *arguments],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, _stderr = process.communicate(timeout=60)
    return process.pid, process.returncode, stdout.strip()


def _live_check(database_url: str) -> None:
    os.environ["COCKROACH_DATABASE_URL"] = database_url
    apply_migration(database_url, MIGRATION)
    apply_migration(database_url, MIGRATION)
    schema_errors = verify_p2_schema(database_url)
    if schema_errors:
        raise RuntimeError("; ".join(schema_errors))

    writer_pid, writer_code, writer_output = _run_worker(["--worker-write"])
    if writer_code != 0:
        raise RuntimeError(f"writer process failed: {writer_output}")
    write_result = json.loads(writer_output)
    if not isinstance(write_result, dict):
        raise RuntimeError("writer process returned invalid evidence")
    reader_arguments = [
        "--worker-read",
        str(write_result["run_id"]),
        str(write_result["step"]),
        str(write_result["actions"]),
        str(write_result["outcomes"]),
    ]
    reader_pid, reader_code, reader_output = _run_worker(reader_arguments)
    if reader_code != 0 or reader_output != '{"restored":true}':
        raise RuntimeError(f"reader process failed: {reader_output}")
    if writer_pid == reader_pid:
        raise RuntimeError("process-boundary verification reused the same process")
    print("[PASS] P2 live migration and schema checks")
    print("[PASS] Process A persisted and exited; fresh Process B restored the run")
    print("P2 Gate: PASS")


def _safe_worker_failure(error: Exception) -> int:
    print(
        json.dumps(
            {
                "error_type": type(error).__name__,
                "sqlstate": getattr(error, "sqlstate", None),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="run credential-free checks only")
    parser.add_argument("--live", action="store_true", help="require the real CockroachDB gate")
    parser.add_argument("--worker-write", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--worker-read",
        nargs=4,
        metavar=("RUN", "STEP", "ACTIONS", "OUTCOMES"),
        help=argparse.SUPPRESS,
    )
    arguments = parser.parse_args()
    database_url = _database_url()

    if arguments.worker_write:
        if database_url is None:
            return 2
        try:
            return _worker_write(database_url)
        except Exception as error:
            return _safe_worker_failure(error)
    if arguments.worker_read is not None:
        if database_url is None:
            return 2
        run, step, actions, outcomes = arguments.worker_read
        try:
            return _worker_read(database_url, UUID(run), int(step), int(actions), int(outcomes))
        except Exception as error:
            return _safe_worker_failure(error)

    try:
        _local_checks()
        if arguments.local:
            return 0
        if database_url is None:
            print(
                "[BLOCKED] COCKROACH_DATABASE_URL is not configured in the "
                "environment or ignored .env"
            )
            print("P2 Gate: BLOCKED - follow NEEDS_USER_ACTION in STATUS.md")
            return 2
        _preflight_database_url(database_url)
        _live_check(database_url)
        return 0
    except Exception as error:
        print(
            f"[FAIL] P2 verification failed safely: {type(error).__name__} "
            f"(sqlstate={getattr(error, 'sqlstate', None)})"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
