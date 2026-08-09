# STATUS

Current phase: P3 — CockroachDB vector memory and validity
State: **PASS — GATE P3 SATISFIED**

## NEEDS_USER_ACTION — AWS REPLAY/P4 RUNTIME BLOCKER

The genuine live P3 Gate passed and generated evidence before closeout. During
the final repeat run, Bedrock began returning only `ThrottlingException` in
both `eu-west-2` and `eu-west-1`. Secret-safe checks confirm STS still passes
and the model remains account-visible. The account's applied Amazon Bedrock
quotas in `eu-west-2` currently show `0.0` for both on-demand requests per
minute and tokens per minute for Amazon Titan Text Embeddings V2; both are
reported as non-adjustable through the normal Service Quotas control.

Exact recovery:

1. Open the AWS Console in `eu-west-2`, go to **Service Quotas -> AWS services
   -> Amazon Bedrock**, and search for `Amazon Titan Text Embeddings V2`.
2. Confirm the applied values for **On-demand model inference requests per
   minute** and **On-demand model inference tokens per minute**.
3. Because the current quotas are non-adjustable in that view, open the
   [AWS Support service-limit form](https://console.aws.amazon.com/support/home#/case/create?issueType=service-limit-increase)
   and request non-zero baseline on-demand RPM and TPM for model
   `amazon.titan-embed-text-v2:0` in `eu-west-2`. State that the account has
   zero baseline quota, rather than asking for capacity above an existing
   allocation.
4. Alternatively, authenticate the AWS CLI to a Hackathon AWS account that has
   non-zero actual invocation quota for this model and Region.
5. Do not paste the Support case, account identity, quota response, credentials,
   or ARN into chat or repository files. When enabled, reply only:
   `Bedrock 配额已启用`.

This external quota state does not falsify the already captured successful
Bedrock invocation and live CockroachDB Gate evidence. It does block a fresh
P3 replay and operational P4 Bedrock work until AWS restores invocation quota.

## P3 live closeout — 9 Aug 2026

- Confirmed clean `d237666`, synchronized `main`, and ignored/untracked `.env`,
  then re-ran the real P2 gate before applying any P3 schema change.
- Secret-safe STS verification succeeded after AWS CLI login. No account ID,
  user ID, ARN, credential, or token was printed or recorded.
- The account-visible Bedrock API confirmed the selected embedding model in
  `eu-west-2`. A real Amazon Titan Text Embeddings V2 invocation using
  `amazon.titan-embed-text-v2:0` returned the configured 512 dimensions.
- Added a production Bedrock provider with dimension/finite-number validation,
  bounded timeouts/retries, secret-safe errors, and no fake fallback. The
  explicitly TEST-ONLY deterministic provider cannot be persisted as live
  evidence.
- Added four canonical Observation -> Action -> Outcome -> Lesson memories
  grounded in P2 identifiers: stale-resource recovery, failed `calibration_A`
  plus successful `reduce_drive_10_percent`, superseded calibration v1 gain
  4.2, and active calibration v2 gain 3.8.
- Applied additive `002_vector_memory.sql` twice. The live column is
  `VECTOR(512)` and `ix_memories_embedding_cosine` is a cosine vector index.
  The migration uses only the required session-level
  `sql_safe_updates=false`; no cluster-wide safety setting was changed.
- Live CockroachDB cosine retrieval placed the expected Scenario B
  intervention at rank 1 of top-3, preserving its P2 observation/action/outcome
  links, prior action, and successful measured outcome.
- The calibration query returned active v2 at rank 1 and superseded v1 at rank
  2. v1 remains visible with `eligible_for_action=false`; the eligible evidence
  collection contains only active v2.
- Generated `docs/evidence/p3-vector-memory.json` from the live verifier. It
  truthfully records that the optimizer did not select the vector index for the
  four-row synthetic dataset, while the index exists and live cosine search ran
  inside CockroachDB.
- P2 remained valid after the additive migration: all eight live integration
  tests passed with zero skips and the real two-process restore passed again.

## P3 verification results

- `uv run --extra dev pytest tests/unit -ra` — PASS, 100 tests.
- Live `uv run --extra dev pytest tests/integration -q -rs` — PASS, 8 tests,
  0 skipped; the ignored URL was loaded only into the child process.
- `uv run --extra dev python scripts/verify_p3.py` — PASS against real Bedrock
  and CockroachDB when Gate evidence was generated; Gate A and Gate B passed.
- Final repeat attempts — BLOCKED externally by Bedrock `ThrottlingException`;
  applied Titan V2 on-demand RPM and TPM now both report `0.0`. Authentication
  and account-visible model listing still pass.
- `uv run --extra dev python scripts/verify_p2.py --live` — PASS after P3;
  migration, schema, and fresh-process recovery passed.
- `uv run --extra dev python scripts/verify_p0.py` — PASS, 7/7 checks.
- P1 Scenario A/B CLI plus identical-run determinism comparison — PASS.
- P2/P3 credential-free verifier modes — PASS and explicitly not counted as
  live gate evidence.
- Ruff lint/format — PASS; strict mypy — PASS over 24 source files; compileall
  and `git diff --check` — PASS.

## P3 bugs discovered and fixed

- Boto3's AWS login provider required the optional CRT dependency;
  `botocore[crt]` is now explicit and failures remain secret-safe.
- CockroachDB reports `format_type(...)` as `vector` while storing the declared
  dimension in `pg_attribute.atttypmod`; verification now uses both and
  cross-checks `SHOW CREATE TABLE`.
- The `pytest` console entry point did not reliably expose repository-root
  imports; pytest now has an explicit project python path.
- Final live reruns exposed SDK default-Region ambiguity and Bedrock throttling.
  Boto sessions now receive the configured Region directly, transient retries
  use bounded exponential backoff, redundant calls were removed, and unchanged
  production vectors are reused only after canonical text plus provider/model/
  dimension checks pass. Each live Gate rerun still embeds both query contexts.

## P3 technical debt

- The optimizer chose a non-vector plan for four rows. P9 may add a modest
  deterministic corpus for realistic plan evidence; no plan was forced or
  fabricated in P3.
- `actions.memory_ids` is ready and persisted by P2, but P3 does not claim that
  a later action has been influenced. P4 must populate it only when an actual
  memory-informed decision executes.
- Bedrock reasoning, MCP, UI, Lambda/API Gateway, S3, and PyVISA remain later
  phases and were not started.
- Current Bedrock on-demand quota must be restored before P4 can execute its
  real model path or the P3 live verifier can be replayed from scratch.

## P3 files changed

- `README.md`, `RUNBOOK.md`, `STATUS.md`, `TODO.md`, `pyproject.toml`, `uv.lock`
- `backend/app/settings.py`, `backend/app/db/migrations.py`
- `backend/app/memory/__init__.py`, `embedding.py`, `episodes.py`, `models.py`,
  `policy.py`, `repository.py`, `retrieval.py`, `schema.py`
- `migrations/002_vector_memory.sql`, `scripts/verify_p3.py`
- `docs/evidence/README.md`, `docs/evidence/p3-vector-memory.json`
- `tests/integration/test_vector_memory.py`
- `tests/unit/test_embedding.py`, `test_memory_episodes.py`,
  `test_memory_policy.py`, `test_memory_retrieval.py`, `test_p3_migration.py`,
  `test_vector_repository.py`

## Next authorization

P4 is protocol-authorized by the exact written Gate P3, but its live Bedrock
work is operationally blocked by the AWS quota issue above. P4 was not started
in this invocation.

## Closeout credential rotation — RESOLVED

On 9 Aug 2026 the user rotated the dedicated LabLedger SQL user's password,
saved the replacement password outside the repository, and replaced the
ignored local `.env` assignment with a complete connection URL. A secret-safe
shape check confirmed exactly one complete URL candidate without displaying
its value. The old credential is no longer used by the project.

The four live integration tests then passed with zero skips, and the standard
live verifier again passed migration/schema checks plus the fresh-process
restore boundary. `.env` remains ignored and untracked. There is no remaining
hard P2 closeout blocker.

## Historical P2 phase goal

Persist P1's typed scenario traces as structured CockroachDB rows through an
explicit psycopg 3 repository, with an equivalent local fake, atomic outcome
and checkpoint transactions, bounded CockroachDB serialization retries, seeded
hero evidence, and a real two-process restart verification path. P2 does not
add vector columns/indexes, MCP, Bedrock, frontend, API, or agent reasoning.

## P1 checkpoint protected

- Inspected Git status, unstaged/staged diffs, ignore rules, and credential-like
  patterns before changing P2 code.
- Confirmed `.env` and `.venv` are ignored and untracked.
- Re-ran all P1 tests, lint, formatting, strict mypy, compile, deterministic CLI,
  P0 verifier, and clean-diff checks.
- Fixed one Ruff formatting failure in `scripts/verify_p0.py` and one trailing
  blank-line failure in `pyproject.toml`, then re-ran the gates.
- Created logical P1 checkpoint commit `000df3b` and pushed it to
  `origin/main`. Local and remote `main` matched before P2 work began.

## P2 implementation and live closeout

- Added `psycopg[binary]>=3.2,<4` as the only runtime database dependency; no
  SQLAlchemy or second persistence system was introduced.
- Added `migrations/001_init.sql` with exactly 11 P2 tables, UUID primary keys,
  JSONB state, TIMESTAMPTZ evidence, explicit constraints/indexes, and no
  vector column/index or destructive statements.
- Added `trace_order` and application audit `sequence_no` so observation,
  action, and outcome evidence can be reconstructed without timestamp guesses.
- Added strict P1 trace validation before any SQL: positive/contiguous/global
  order, known device IDs, exactly one linked outcome per action, matching
  action/outcome device, and success/error consistency.
- Added deterministic logical-device and record UUID mapping. Repeated action
  types remain distinct, failed outcomes are preserved, and Scenario B keeps
  the signal-source action linked to the correct device.
- Added defensive JSON copies so a frozen P1 record's mutable dictionaries
  cannot mutate fake or mapped persistence after insertion.
- Added checkpoint state sufficient for a fresh process to restore scenario,
  seed, current/next step, explicit device connections/resources, active
  faults, drive amplitude, calibration, MUX state, completed action IDs, last
  action, and pending action. The mapper no longer infers connection state from
  unrelated observations or outcomes.
- Added an explicit repository protocol, psycopg 3 implementation with
  parameterized SQL, and copy-on-write fake.
- Implemented the critical transaction boundary: action terminal update,
  outcome insert, compare-and-set run progress/context, checkpoint insert, and
  audit insert. External device work is outside the retry boundary.
- Added bounded whole-transaction retry for SQLSTATE `40001` only. UUIDs,
  timestamps, and command records are allocated before retry.
- Added persistence fingerprints and conflict-on-divergence semantics. An exact
  replay is idempotent; reusing a run ID with different evidence is rejected.
- Added shared repository validation for run/action/outcome/checkpoint/audit
  identity, pending/completed action state, terminal outcome consistency, and
  calibration ownership.
- Strengthened live schema verification from table-name presence to required
  columns, UUID primary keys, and critical named constraints.
- Fixed simulator state invariants: failed reconnects clear stale connected
  resources, rediscovery resolves stale-resource faults, wrong-device clears
  cannot erase shared effects, and multi-device fault ownership is refcounted.
- Added structured hero seed evidence for connection failure/recovery,
  temperature/noise anomaly, failed Calibration A, successful drive reduction,
  calibration v1 gain 4.2 as superseded, and calibration v2 gain 3.8 as active.
- Added `scripts/verify_p2.py`: local mode validates schema/mapping/fake; live
  mode applies the migration twice, introspects the real schema, runs Process A
  to persist and exit, then runs a fresh Process B to restore and validate.
- Added four live CockroachDB tests. All four ran against the real cluster and
  passed; no integration test was skipped in the final gate.
- Live execution exposed two Windows configuration failures before the gate:
  a password-only `.env` value and a missing Cloud CA certificate. Added a
  secret-safe URL/TLS preflight with six regression tests and documented the
  official `root.crt` setup while retaining `sslmode=verify-full`.

## Failure-led improvements

Three read-only review agents independently audited P1 failure paths, P2 schema,
and P2 transactions. Their findings became tests or explicit debt:

- Scenario A's two `connect` attempts cannot collide by action type.
- Failed connection/calibration outcomes cannot be filtered out.
- Cross-table trace order cannot depend on equal transaction timestamps.
- Fake reads/writes cannot share mutable JSON aliases.
- Duplicate order, orphan outcome, missing outcome, unknown device, and
  success-with-error traces fail before persistence.
- Four injected transaction failures — after action, outcome, run, and
  checkpoint writes — all leave the fake at its pre-transaction state.
- Retry tests prove first-retry success, exact maximum attempts, immediate
  propagation of non-`40001`, and stable business identity across attempts.

## First-principles verdict

LabLedger succeeds only when durable prior evidence changes a later safe action
and the measured outcome becomes new memory. Current factual coverage is:

- Observe realistic synthetic faults and measured outcomes — implemented and
  locally verified.
- Persist structured episodes/checkpoints — implemented and verified against
  the real CockroachDB cluster across two fresh operating-system processes.
- Retrieve semantically related episodes — implemented and verified with real
  Bedrock embeddings plus a live CockroachDB cosine top-k query.
- Reject stale/superseded facts during current-action evidence selection —
  implemented deterministically; P4 still owns actual action execution.
- Prove memory-on chooses differently from memory-off — not implemented.
- Resume a running agent without duplicate execution — explicit state is now
  captured, but continuation execution is not implemented.
- Exercise AWS Bedrock embeddings — verified in P3. Managed MCP, AWS-hosted
  runtime, judge UI, public demo URL, and video are not yet implemented.
- The P3 change adds vector memory and Bedrock embeddings but intentionally no
  MCP, frontend, API, or agent-reasoning implementation.

## Final closeout rerun — 9 Aug 2026

- Pre-commit candidate scan passed with zero high-confidence secret matches;
  `.env` is ignored and untracked.
- Final local rerun passed: 69 unit tests, Ruff lint, Ruff format check, strict
  mypy over 15 source files, compileall, P0 regression verification, P2 local
  verification, Scenario A/B CLI checks, deterministic Scenario B repeat, and
  `git diff --check`.
- An initial integration invocation correctly skipped because pytest does not
  automatically import `.env`; this invocation was not counted as Gate
  evidence. The URL was then loaded into that child process only, without
  printing it, and all four live tests passed with zero skips.
- Hardened integration-test collection to call the same secret-safe URL/TLS
  preflight before psycopg. A captured regression check proves invalid
  configuration now fails without echoing its value; all 69 unit tests and
  static checks still pass afterward.
- `scripts/verify_p2.py` passed live migration/schema verification and the
  Process A write/exit -> fresh Process B restore boundary after credential
  rotation.
- The final candidate scan covered 38 tracked/untracked non-ignored files with
  zero high-confidence secret findings; `.env` is ignored and untracked.

## Verification results

- `.\.venv\Scripts\python -m pytest tests/unit -ra` — PASS, 69 tests.
- `.\.venv\Scripts\python -m pytest tests/integration -m integration -ra` —
  PASS, 4 live tests, 0 skipped.
- `.\.venv\Scripts\python -m ruff check .` — PASS.
- `.\.venv\Scripts\python -m ruff format --check backend tests scripts` —
  PASS after formatting the new files.
- `.\.venv\Scripts\python -m mypy backend/app` — PASS, strict mode, 15
  source files.
- `.\.venv\Scripts\python scripts\verify_p2.py --local` — PASS; explicitly
  reports that fake evidence cannot satisfy Gate P2.
- `.\.venv\Scripts\python scripts\verify_p2.py` — PASS against the live
  cluster: migration/schema verification plus Process A/Process B restore.
- Live read-only hero-evidence query — PASS: Scenario A ordered failure and
  recovery; Scenario B anomaly, failed calibration, successful drive reduction,
  and measured improvement; calibration v1/v2 values, validity, supersession,
  confidence, provenance, and device ownership.

## Live Gate P2 evidence

- Process A connected to the real cluster, applied `001_init.sql` twice,
  introspected all 11 tables/columns/UUID primary keys/named constraints,
  persisted the deterministic scenario, structured actions/outcomes/audit and
  latest checkpoint, then exited.
- Process B was a genuinely fresh Python process. It independently reconnected
  and restored the run, stable scenario state, seed, contiguous ordered
  timeline, failed evidence, run progress, explicit device/physical state,
  latest checkpoint, completed-action IDs, last action, and no pending action.
- Restored action/outcome counts matched Process A, so the read/restart path did
  not create a duplicate completed action.
- The live rollback integration test forced a late uniqueness failure and
  proved action, outcome, run progress, and checkpoint changes all rolled back.
- The bounded SQLSTATE `40001` behavior remains covered by complete-operation
  retry tests with stable preallocated UUID/time identity. A naturally occurring
  serialization conflict was not required or fabricated.

### Live compatibility fix

- Created a dedicated application SQL user and restricted the Cloud IP Allowlist
  to the current development IP.
- Downloaded the cluster's public CA to the standard Windows PostgreSQL path,
  verified that it is a PEM certificate with no private key, and retained full
  certificate/hostname verification.
- Added preflight failures for incomplete/password-only URLs, unresolved
  password placeholders, non-`verify-full` URLs, and a missing Windows CA.
- No database URL, username/password, cluster UUID, IP, account identity, token,
  or key was printed or committed.

## PARALLEL PREREQUISITES

- The user reported Devpost registration complete. A saved LabLedger project
  draft has not been verified from user-provided evidence; this is important
  for submission readiness but is not Gate P2.
- AWS CLI identity, account-visible embedding-model selection, and a real
  embedding invocation are now verified. P4 must separately select and verify
  its reasoning model before relying on it.
- Managed MCP credentials/integration are a later phase and were not started.
- `ccloud` remains optional.

## Files changed in P2

- `README.md`
- `RUNBOOK.md`
- `STATUS.md`
- `TODO.md`
- `pyproject.toml`
- `backend/app/db/__init__.py`
- `backend/app/db/fake.py`
- `backend/app/db/mapping.py`
- `backend/app/db/migrations.py`
- `backend/app/db/psycopg_repository.py`
- `backend/app/db/repository.py`
- `backend/app/db/types.py`
- `backend/app/devices/scenarios.py`
- `backend/app/devices/simulator.py`
- `backend/app/models/trace.py`
- `migrations/001_init.sql`
- `scripts/verify_p2.py`
- `tests/unit/test_db_mapping.py`
- `tests/unit/test_fake_repository.py`
- `tests/unit/test_migration.py`
- `tests/unit/test_repository_sql.py`
- `tests/unit/test_transaction_retry.py`
- `tests/unit/test_verify_p2.py`
- `tests/unit/test_faults.py`
- `tests/unit/test_scenarios.py`
- `tests/integration/test_cockroach_repository.py`

## Commands actually run in this invocation

- Read the attached P2 request and `AGENTS.md`, `TODO.md`, `RUNBOOK.md`, and
  `STATUS.md` in full before editing.
- Inspected Git status/diffs/staged files, ignore rules, remote, configuration
  presence, and credential-pattern filenames/content without displaying secret
  values.
- Re-ran P1 pytest, Ruff lint/format, strict mypy, compileall, P0 verification,
  Scenario A/B CLI, deterministic seed comparison, and `git diff --check`.
- Staged the P1 files, ran staged diff/forbidden-name checks, committed P1, and
  pushed `main`.
- Installed the updated editable package with `psycopg 3` and development tools.
- Ran Ruff formatting/lint repeatedly while closing reported failures.
- Ran strict mypy and fixed every reported mapper type error.
- Ran all 69 unit tests after adding the live-configuration regressions.
- Ran all four live CockroachDB integration tests with zero skips.
- Ran the live P2 verifier: Process A persisted and exited; a fresh Process B
  independently restored the run and checkpoint.
- Ran secret-safe read-only SQL checks for Scenario A, Scenario B, and
  calibration v1/v2 hero evidence.
- Re-ran Ruff lint/format, strict mypy, compileall, P0 verification, Scenario
  A/B CLI, and `git diff --check` after the live fixes.

## Technical debt

- `devices.active_calibration_id` is an application-validated UUID in P2 rather
  than a database foreign key because it creates a cyclic DDL dependency with
  `calibrations.device_id`; adding it idempotently should be handled in a later
  numbered migration after the live schema is verified.
- The explicit checkpoint is now sufficient to reconstruct simulator state,
  but no agent state machine exists yet to instantiate a new adapter and
  continue execution without duplicating a completed action. That is a later
  gate, not evidence already achieved by P2.
- `device_sessions` exists in the schema but Scenario A does not yet populate
  session-specific rows; its connection evidence currently lives in typed
  observations/actions/outcomes/audit records.
- The final lock strategy is still pending as later runtime dependencies settle.

## Historical P2 gate verdict

**P2 PASS — exact Gate P2 criteria were satisfied. P3 was authorized and has
since passed; the current authorization is recorded at the top of this file.**
