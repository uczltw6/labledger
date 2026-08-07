# STATUS

Current phase: P1 — Local deterministic lab simulator
State: **PASS — GATE P1 SATISFIED**

## Phase goal

Build the smallest Python 3.12 simulator/domain foundation that exposes four
devices, behavior-changing deterministic faults, stable machine-readable
scenario traces, and reproducible Scenario A/B CLI runs without cloud, LLM,
database, frontend, MCP, embeddings, agent reasoning, or PyVISA dependencies.

## Gate P1 result

The documented command:

```powershell
.\.venv\Scripts\python -m backend.app.devices.simulator --scenario all --json
```

runs both P1 scenarios and emits canonical JSON containing:

- stable scenario ID and explicit deterministic seed;
- typed observations with device ID, observation type, payload, and order;
- attempted actions with device ID, action type, parameters, and order;
- outcomes with success/failure, result/error, linked action order, and order.

**Gate P1 verdict: PASS.** P2 is authorized, but no P2 database schema,
repository, migration, seed, or integration-test work was started.

## Completed

- Added a minimal Python 3.12 package and development-tool configuration.
- Added dependency-free simulator trace contracts using typed dataclasses.
- Defined the complete `DeviceAdapter` interface:
  `discover`, `connect`, `identify`, `read_settings`, `write_safe_setting`,
  `acquire`, `self_test`, and `disconnect`.
- Implemented four synthetic devices:
  `signal_source_01`, `scope_01`, `mux_01`, and `temperature_01`.
- Implemented explicit connection states: `disconnected`, `connected`, and
  `fault`.
- Implemented all required stable fault identifiers:
  `CONNECTION_TIMEOUT`, `STALE_RESOURCE`, `WRONG_IDENTITY`,
  `MUX_CHANNEL_SWAP`, `CALIBRATION_SUPERSEDED`, `TEMPERATURE_DRIFT`,
  `NOISE_RISE`, `SIGNAL_COLLAPSE`, and `TOOL_TIMEOUT`.
- Faults alter real simulator behavior or shared physical state; they are not
  display-only labels.
- Implemented Scenario A as a stale-resource connection failure followed by
  rediscovery, reconnect, identity verification, and an observable recovery.
- Implemented Scenario B as a deterministic high-temperature/high-noise/low-
  quality anomaly with the truthful baseline sequence:
  `calibration_A -> FAILED -> reduce_drive_10_percent -> SUCCESS`.
- The successful Scenario B intervention is derived from the shared signal
  model: noise falls and signal quality rises after drive reduction.
- Kept scenario orchestration separate from device behavior so later phases can
  compare action strategies without rewriting the simulator.
- Added machine-readable JSON and concise human-readable CLI output.
- Added unit tests for all four devices, every required fault, connection
  transitions, safe-setting validation, Scenario A/B, measurable improvement,
  CLI JSON, and deterministic reproduction.
- Updated README with the Python 3.12 setup and one-command Scenario A/B run.

## Verification

- `.\.venv\Scripts\python -m pytest -q` — PASS, 27 tests.
- `.\.venv\Scripts\python -m ruff check .` — PASS.
- `.\.venv\Scripts\python -m ruff format --check backend tests` — PASS,
  12 files already formatted.
- `.\.venv\Scripts\python -m mypy backend/app` — PASS, no issues in 8 source
  files under strict mode.
- `.\.venv\Scripts\python -m compileall -q backend tests scripts` — PASS.
- Scenario A JSON CLI — PASS; emitted the stable
  `scenario-a-connection-recovery-v1` trace with observations, four attempted
  actions, and four outcomes.
- Scenario B JSON CLI — PASS; emitted the stable
  `scenario-b-anomaly-baseline-v1` trace with the required failed calibration,
  successful drive reduction, and measured before/after values.
- Documented `--scenario all --json` command — PASS; emitted both traces with
  non-empty observations, attempted actions, and outcomes.
- Scenario B with seed `707`, executed twice — PASS; canonical JSON outputs
  were byte-for-byte identical.
- `.\.venv\Scripts\python scripts\verify_p0.py` — PASS, 7/7; P1 changes did
  not break repository/compliance checks.
- `git diff --check` — PASS after the closeout update.

## Dependencies added

Runtime dependencies: **none**. The simulator core uses only Python 3.12's
standard library.

Development dependencies in `pyproject.toml`:

- `pytest>=8.3,<9` — P1 unit and CLI acceptance tests; installed version 8.4.2.
- `ruff>=0.9,<1` — linting and formatting; installed version 0.16.2.
- `mypy>=1.14,<2` — strict type checking for domain and simulator contracts;
  installed version 1.20.2.

`setuptools>=75` is used only as the package build backend.

## Files changed in P1

- `pyproject.toml`
- `README.md`
- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/models/__init__.py`
- `backend/app/models/trace.py`
- `backend/app/devices/__init__.py`
- `backend/app/devices/base.py`
- `backend/app/devices/faults.py`
- `backend/app/devices/simulator.py`
- `backend/app/devices/scenarios.py`
- `tests/unit/test_devices.py`
- `tests/unit/test_faults.py`
- `tests/unit/test_scenarios.py`
- `scripts/verify_p0.py` — removed one extra blank line so repository-wide Ruff
  import formatting passes; no P0 behavior changed.
- `TODO.md`
- `STATUS.md`

The worktree also contains a pre-existing `.env.example` modification from P0;
P1 did not change it. `.venv` and generated package metadata are ignored.

## Commands actually run

- Read `AGENTS.md`, `TODO.md`, `RUNBOOK.md`, and `STATUS.md` in full before
  editing.
- Inspected repository files, Git status, Python version, and test-tool
  availability.
- `python -m compileall -q backend`.
- `python -m venv .venv`.
- `.\.venv\Scripts\python -m pip install --upgrade pip`.
- `.\.venv\Scripts\python -m pip install -e ".[dev]"`.
- `.\.venv\Scripts\python -m compileall -q backend tests scripts`.
- `.\.venv\Scripts\python -m pytest -q`.
- `.\.venv\Scripts\python -m ruff check .`.
- `.\.venv\Scripts\python -m ruff format backend tests`.
- `.\.venv\Scripts\python -m ruff format --check backend tests`.
- `.\.venv\Scripts\python -m mypy backend/app`.
- `.\.venv\Scripts\python -m backend.app.devices.simulator --scenario scenario-a --json`.
- `.\.venv\Scripts\python -m backend.app.devices.simulator --scenario scenario-b --json`.
- `.\.venv\Scripts\python -m backend.app.devices.simulator --scenario all --json`.
- Repeated Scenario B twice with seed `707` and compared canonical JSON output.
- `.\.venv\Scripts\python scripts\verify_p0.py`.

## Technical debt

- `pyproject.toml` constrains direct development dependencies but no lockfile is
  committed yet. Add the repository's final lock strategy once later phases
  settle the runtime dependency set.
- P1 has no coverage threshold; behavior is covered by 27 focused tests, but a
  coverage gate may be added during product-readiness work.
- The simulator is synchronous by design. Any future hardware adapter must keep
  the same domain semantics while deciding separately how to handle blocking
  I/O.
- Memory-on/memory-off strategy selection is intentionally not implemented in
  P1; later phases can supply different orchestrators over the existing device
  API and trace records.

## Blockers

None for Gate P1.

The previously documented cloud credentials, database connectivity, Bedrock
visibility, region-alignment, and Devpost-draft items remain parallel
prerequisites for their later phases; they were not revisited in P1.

## Next

- P2 is authorized.
- Start P2 only in a new invocation explicitly scoped to CockroachDB structured
  memory.
- Do not add vector search until P3.
