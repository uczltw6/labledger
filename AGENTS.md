# LabLedger — Codex Master Instructions

> Persistent operational + experimental memory for autonomous laboratory agents.
> Tagline: **Agents should not only remember what was said. They should remember what happened.**

## 0. Purpose of this file

This file is the source of truth for Codex while building the CockroachDB × AWS Hackathon submission. Read it fully before modifying code. Also read `TODO.md` and `RUNBOOK.md`.

Do not silently simplify the product into a chatbot or generic RAG demo. The core product is a long-running laboratory operations agent whose past observations, actions, failures, recoveries, experiment results, and device state persist across sessions and change future actions.

If a credential or cloud-console action is required and cannot be performed safely from the current environment, stop that sub-step, write `NEEDS_USER_ACTION` with exact instructions, and continue all independent work.

---

# 1. Competition constraints that are non-negotiable

The submission must:

1. Be an agentic application using CockroachDB as the persistent memory layer.
2. Store, retrieve, **and act on** memory.
3. Use at least two CockroachDB tools. This project will use:
   - **CockroachDB Distributed Vector Indexing** as a runtime feature.
   - **CockroachDB Cloud Managed MCP Server** as a runtime/agent access path.
   - Optional bonus: ccloud CLI and official CockroachDB Agent Skills during development/operations.
4. Use at least one AWS service. This project will intentionally use several:
   - Amazon Bedrock model invocation for reasoning and embeddings where available.
   - AWS Lambda for agent/API execution.
   - Amazon S3 for experiment artifacts/raw files.
   - API Gateway for the public API.
   - S3 + CloudFront for the static frontend if practical.
   - AWS Secrets Manager for credentials if time permits.
5. Provide a public open-source repository with a visible open-source license, setup instructions, dependencies, example configuration/data, and runnable code.
6. Provide a functional demo URL.
7. Provide a public YouTube/Vimeo video under 3 minutes that visibly demonstrates CockroachDB memory at work.

Deadline target: finish and submit before 18 Aug 2026 22:00 Europe/London; do not use the deadline itself as the planned finish time.

---

# 2. Product definition

## 2.1 Working name

**LabLedger**

Subtitle: **Persistent Memory for Autonomous LabOps**

One-line pitch:

> LabLedger is an AI lab-operations agent that remembers device state, connection failures, calibration changes, experiment observations, interventions, and outcomes, then uses those memories to safely make better decisions in future runs.

## 2.2 Origin / product insight

Real experimental work has two coupled problems:

1. **Scientific memory is fragmented**: results live in notebooks, CSVs, scripts, plots, chat, and researchers' heads.
2. **Operational memory is even more fragile**: instrument connection quirks, stale addresses, channel mappings, calibration versions, retry sequences, known bad configurations, manual interventions, and the reason a run failed are often not captured as reusable machine-readable knowledge.

A model that only sees the current prompt can repeat the same failed troubleshooting step or use a superseded calibration. LabLedger turns the history of the lab into durable, queryable experience.

The key innovation is not “chat with lab data.” It is:

> **Experiential learning without model retraining:** the agent changes future action selection because prior episodes, outcomes, and validity state are persisted and retrieved.

## 2.3 User

Primary user:
- Experimental scientist / research engineer operating long-running instrumented experiments.

Secondary user:
- Lab manager / industrial sensing engineer who needs reproducibility, handover, diagnosis, and auditability.

## 2.4 MVP scope

Build one reproducible mixed-instrument test bench, simulated by default:

- Signal generator / source
- Oscilloscope or digitizer / acquisition device
- Multiplexer (MUX)
- Temperature/environment sensor

The same abstraction should support an optional local real-instrument adapter later through PyVISA/SCPI, but **real hardware is not required for the hackathon MVP**.

The simulator must be deterministic enough to reproduce demo failures.

---

# 3. The four hero scenarios

Everything built must support these four scenarios. Avoid features that do not strengthen one of them.

## Scenario A — Device connection failure becomes reusable operational memory

Run 001:
1. Agent tries to connect to `scope_01`.
2. Connection fails with a synthetic timeout/resource mismatch.
3. Agent inspects device state and retrieves prior troubleshooting knowledge if any.
4. It applies a safe recovery sequence: rediscover -> validate identity -> reconnect.
5. Recovery succeeds.
6. It writes an episode containing observation, attempted action, error, successful recovery, and evidence.

Run 018 / new session:
1. A semantically similar connection fault occurs.
2. Agent retrieves Run 001.
3. It avoids a known ineffective step and immediately chooses the successful recovery sequence.
4. UI explicitly shows **“Memory changed action.”**

Acceptance signal: the recommended/action sequence differs when memory is enabled versus disabled.

## Scenario B — Experimental outcome memory changes intervention

Prior run:
- High temperature + rising noise + falling signal quality.
- `Calibration A` was attempted and failed.
- Reducing drive amplitude by 10% restored signal quality.

Current run:
- Similar signature appears.
- Vector retrieval returns the prior episode.
- Agent explains why it is relevant.
- Agent avoids repeating the failed calibration and chooses the previous successful intervention, subject to policy.
- Outcome is measured and persisted as a new episode.

Acceptance signal: store -> retrieve -> act -> verify -> learn is visible end-to-end.

## Scenario C — Superseded calibration is remembered but not treated as current truth

Data:
- Calibration v1: gain=4.2, valid until T2.
- Calibration v2: gain=3.8, active from T2 onward; v1 is superseded by v2.

Current task:
- Semantic search may retrieve both v1 and v2.
- Memory policy must filter/rank based on validity.
- Agent must use v2 for current action.
- UI can still display v1 as historical evidence with a `SUPERSEDED` badge.

Acceptance signal: stale-memory rejection test passes.

## Scenario D — Agent process dies and resumes safely

1. Start an experiment.
2. Complete several steps.
3. Persist checkpoint/task state.
4. Simulate process termination or new session.
5. Restart agent.
6. Rehydrate:
   - run id
   - current step
   - device states
   - last safe action
   - pending approval/action
   - relevant memories
7. Continue without duplicating a completed risky action.

Acceptance signal: restart continuity test passes and audit trail shows no duplicate action.

---

# 4. What NOT to build

Do not spend critical-path time on:

- Generic document Q&A.
- Generic customer-support chat.
- Multi-agent theatre with multiple personas and no need for them.
- A full electronic lab notebook replacement.
- Real hardware drivers for many vendors.
- Computer vision.
- Training a model.
- Complex autonomous optimization algorithms.
- A huge knowledge graph UI.
- Authentication systems beyond what is necessary to demonstrate scoped access.
- A separate vector database.

If a feature does not strengthen a judging criterion or one of the four hero scenarios, put it in `BACKLOG.md` rather than implementing it.

---

# 5. Privacy, IP, and data policy

This public repository must contain **no employer-confidential data** and no proprietary instrument configurations.

Rules:

- Use synthetic experiment names, values, faults, and signals.
- Do not name a current employer in public sample data.
- Do not copy internal code, dashboards, documents, device addresses, cloud URLs, or experiment results.
- The public narrative may truthfully say the product is inspired by experience with academic experimental systems and industrial sensing/automation, but the implementation and demo dataset must be independently created.
- Secrets must never be committed.
- `.env`, API keys, database URLs, AWS credentials, and service-account keys must be gitignored.

---

# 6. Product architecture

Preferred architecture:

```text
Researcher Browser
      |
      v
Static React/Vite UI (S3 + CloudFront)
      |
      v
API Gateway
      |
      v
AWS Lambda: LabLedger Agent/API
      |
      +-----------------------+
      |                       |
      v                       v
Amazon Bedrock          Device Tool Layer
Reasoning/Embedding     Simulator by default
      |                 Optional PyVISA adapter
      |
      v
Memory Policy / Retrieval
      |
      +------------------------------------+
      |                                    |
      v                                    v
CockroachDB Cloud                       Amazon S3
Structured state + VECTOR              raw traces / CSV / JSON
      |
      +-- Distributed Vector Index
      +-- Managed MCP Server
```

Do not introduce another persistent database.

---

# 7. Technology choices

## Backend

- Python 3.12 if supported by deployment target.
- FastAPI-style routing locally; for Lambda either:
  - lightweight Lambda handlers, or
  - FastAPI + Mangum if it materially accelerates development.
- Pydantic v2 models.
- psycopg 3 for deterministic SQL transactions/vector queries.
- Official MCP Python SDK or a minimal well-tested Streamable HTTP MCP client for the managed MCP route.
- boto3 for Bedrock and S3.
- Structured JSON logging.

## Frontend

- React + Vite + TypeScript.
- Keep the UI intentionally small and demo-oriented.
- No design-system dependency that slows delivery.

## Quality

- pytest
- ruff
- mypy for backend core where practical
- frontend lint/typecheck

## Packaging

- `pyproject.toml`
- reproducible lock strategy if available
- `.env.example`
- Docker optional; do not require Docker for local tests if avoidable.

---

# 8. Repository structure

Create/maintain approximately this structure:

```text
.
├── AGENTS.md
├── TODO.md
├── RUNBOOK.md
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── pyproject.toml
├── backend/
│   └── app/
│       ├── api/
│       ├── agent/
│       │   ├── loop.py
│       │   ├── prompts.py
│       │   ├── policy.py
│       │   └── tools.py
│       ├── memory/
│       │   ├── repository.py
│       │   ├── retrieval.py
│       │   ├── consolidation.py
│       │   ├── mcp_client.py
│       │   └── scoring.py
│       ├── devices/
│       │   ├── base.py
│       │   ├── simulator.py
│       │   ├── faults.py
│       │   └── pyvisa_adapter.py   # optional/stretch
│       ├── aws/
│       │   ├── bedrock.py
│       │   └── s3.py
│       ├── db/
│       ├── models/
│       └── settings.py
├── frontend/
├── migrations/
│   ├── 001_init.sql
│   └── 002_vector_index.sql
├── seed/
│   ├── scenarios.json
│   └── seed.py
├── evals/
│   ├── cases/
│   ├── run_evals.py
│   └── README.md
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/
│   ├── bootstrap_local.*
│   ├── seed_demo.*
│   ├── smoke_cloud.*
│   └── verify_submission.*
├── infra/
│   └── template.yaml
└── docs/
    ├── architecture.md
    ├── demo-script.md
    ├── devpost-draft.md
    ├── judging-matrix.md
    └── evidence/
```

Use platform-neutral scripts where easy; if shell scripts are used, also document Windows equivalents because the project owner may work on Windows.

---

# 9. CockroachDB data model

Prefer UUID primary keys generated in the application or with Cockroach-friendly defaults. Avoid sequential primary-key hot spots.

## 9.1 `devices`

Fields:
- `id UUID PRIMARY KEY`
- `lab_id UUID`
- `name STRING`
- `device_type STRING`
- `vendor STRING NULL`
- `model STRING NULL`
- `resource_hint STRING NULL`
- `connection_state STRING`
- `firmware_version STRING NULL`
- `active_calibration_id UUID NULL`
- `metadata JSONB`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

## 9.2 `device_sessions`

Fields:
- `id UUID PRIMARY KEY`
- `device_id UUID`
- `experiment_run_id UUID NULL`
- `started_at TIMESTAMPTZ`
- `ended_at TIMESTAMPTZ NULL`
- `connection_result STRING`
- `identity_response STRING NULL`
- `error_code STRING NULL`
- `error_detail STRING NULL`
- `recovery_action_id UUID NULL`

## 9.3 `experiment_runs`

Fields:
- `id UUID PRIMARY KEY`
- `name STRING`
- `status STRING` (`planned|running|paused|failed|completed`)
- `recipe_version STRING`
- `started_at TIMESTAMPTZ NULL`
- `ended_at TIMESTAMPTZ NULL`
- `current_step INT`
- `context JSONB`
- `created_by STRING`

## 9.4 `observations`

Fields:
- `id UUID PRIMARY KEY`
- `experiment_run_id UUID`
- `device_id UUID NULL`
- `observation_type STRING`
- `payload JSONB`
- `summary STRING`
- `severity STRING`
- `observed_at TIMESTAMPTZ`
- `artifact_id UUID NULL`
- `provenance JSONB`

## 9.5 `actions`

Fields:
- `id UUID PRIMARY KEY`
- `experiment_run_id UUID`
- `device_id UUID NULL`
- `action_type STRING`
- `parameters JSONB`
- `risk_level STRING` (`low|medium|high`)
- `approval_state STRING` (`not_required|pending|approved|rejected`)
- `selected_reason STRING`
- `memory_ids UUID[]` or normalized join table if array handling becomes awkward
- `status STRING`
- `created_at TIMESTAMPTZ`
- `executed_at TIMESTAMPTZ NULL`

## 9.6 `outcomes`

Fields:
- `id UUID PRIMARY KEY`
- `action_id UUID`
- `success BOOL`
- `result JSONB`
- `quality_delta FLOAT8 NULL`
- `error_code STRING NULL`
- `summary STRING`
- `observed_at TIMESTAMPTZ`

## 9.7 `calibrations`

Fields:
- `id UUID PRIMARY KEY`
- `device_id UUID`
- `version STRING`
- `parameters JSONB`
- `status STRING` (`active|superseded|expired|invalid`)
- `valid_from TIMESTAMPTZ`
- `valid_until TIMESTAMPTZ NULL`
- `superseded_by UUID NULL`
- `confidence FLOAT8`
- `provenance JSONB`

## 9.8 `memories`

This is the central long-term memory table.

Fields:
- `id UUID PRIMARY KEY`
- `lab_id UUID`
- `experiment_run_id UUID NULL`
- `device_id UUID NULL`
- `memory_type STRING`
  - `connection_failure`
  - `connection_recovery`
  - `experimental_outcome`
  - `calibration_fact`
  - `intervention_result`
  - `operational_rule`
- `title STRING`
- `content STRING`
- `embedding_text STRING`
- `embedding VECTOR(<EMBEDDING_DIM>)`
- `status STRING` (`active|superseded|expired|disputed`)
- `confidence FLOAT8`
- `valid_from TIMESTAMPTZ`
- `valid_until TIMESTAMPTZ NULL`
- `superseded_by UUID NULL`
- `source_observation_id UUID NULL`
- `source_action_id UUID NULL`
- `source_outcome_id UUID NULL`
- `provenance JSONB`
- `created_at TIMESTAMPTZ`

Create a vector index optimized for the chosen semantic distance. Cosine is preferred for text embeddings.

Where it helps retrieval, consider a prefix column such as `lab_id` or `memory_type`; do not add complexity until verified by query plans.

## 9.9 `agent_checkpoints`

Fields:
- `id UUID PRIMARY KEY`
- `experiment_run_id UUID`
- `step_no INT`
- `agent_state JSONB`
- `last_action_id UUID NULL`
- `pending_action_id UUID NULL`
- `created_at TIMESTAMPTZ`

Constraint: restarting must load the latest valid checkpoint and must not repeat a completed non-idempotent action.

## 9.10 `artifacts`

Fields:
- `id UUID PRIMARY KEY`
- `experiment_run_id UUID`
- `artifact_type STRING`
- `s3_uri STRING`
- `sha256 STRING`
- `metadata JSONB`
- `created_at TIMESTAMPTZ`

## 9.11 `audit_events`

Fields:
- `id UUID PRIMARY KEY`
- `experiment_run_id UUID NULL`
- `actor_type STRING`
- `actor_id STRING`
- `event_type STRING`
- `target_type STRING`
- `target_id UUID NULL`
- `detail JSONB`
- `created_at TIMESTAMPTZ`

This is application-level audit evidence. Do not claim it replaces CockroachDB Cloud audit logs.

---

# 10. Memory architecture

## 10.1 Memory is an episode, not a chat turn

Canonical episode:

```text
Observation -> Decision -> Action -> Outcome -> Lesson
```

A memory should preserve:
- what state was observed
- what action was considered/taken
- what evidence informed the choice
- whether it succeeded
- what changed afterward
- validity/confidence/provenance

## 10.2 Retrieval pipeline

For every decision that can benefit from experience:

1. Build `retrieval_context` from current run/device/observation.
2. Create embedding.
3. ANN query through CockroachDB vector index.
4. Filter/annotate by:
   - active validity
   - device/lab scope
   - memory type
   - permissions
5. Re-rank with deterministic features.
6. Return top memories with an explicit “why retrieved” explanation.
7. Feed structured memory records to the reasoner.
8. Persist which memory IDs influenced the resulting action.

Suggested scoring starting point:

```text
final_score =
  0.55 * semantic_similarity
+ 0.15 * device_context_match
+ 0.10 * confidence
+ 0.10 * recency_or_validity_weight
+ 0.10 * successful_outcome_weight
```

This is a heuristic, not a scientific truth. Make it configurable and test it.

## 10.3 Validity policy

Rules:

- `active`: eligible for current decision.
- `superseded`: visible as history, not eligible as current truth unless the user explicitly asks for historical context.
- `expired`: excluded from current action selection.
- `disputed`: may be shown as weak evidence but cannot alone justify an automated action.

If active and superseded facts conflict, active fact wins. The UI must show the conflict rather than hiding it.

## 10.4 Confidence policy

Suggested semantics:

- 1.0: directly measured/confirmed or deterministic system state.
- 0.7-0.99: strong evidence.
- 0.4-0.69: plausible hypothesis.
- <0.4: weak/unverified observation.

Do not allow a single low-confidence memory to authorize a high-risk action.

## 10.5 Consolidation

Do not create a long-term memory for every telemetry point.

Persist raw observations, then consolidate into long-term memory when at least one is true:
- an action was taken
- an action failed
- a recovery succeeded
- a calibration changed
- an experiment ended
- a human approved/rejected an intervention
- a novel anomaly was confirmed

---

# 11. Agent loop

Implement a small, explicit state machine rather than an opaque autonomous loop.

States:

```text
OBSERVE
  -> RETRIEVE_MEMORY
  -> DIAGNOSE
  -> PROPOSE_ACTION
  -> POLICY_CHECK
  -> APPROVAL_IF_REQUIRED
  -> EXECUTE
  -> VERIFY
  -> WRITE_OUTCOME
  -> CONSOLIDATE_MEMORY
  -> CHECKPOINT
```

The model may reason and select among allowed actions, but deterministic code owns:
- permission checks
- risk classification
- idempotency
- validity filtering
- checkpointing
- database writes
- retry limits
- dangerous-action blocks

## 11.1 Safe action policy

Low risk, may auto-execute in simulator:
- query device identity
- rediscover connection
- reconnect
- read settings
- acquire sample
- run self-test
- retry a read with bounded retries

Medium risk, require user approval in UI:
- apply changed operating parameter within configured safe bounds
- switch MUX channel mapping
- change a calibration reference

High risk / out of MVP:
- destructive device commands
- arbitrary shell execution
- firmware update
- erase/reset
- disabling safety interlocks
- actions beyond simulated safe envelopes

For the public demo, use simulated devices only for automated interventions.

---

# 12. Device simulator

The simulator is a product feature for reproducibility, not a toy afterthought.

Define a common `DeviceAdapter` interface:

- `discover()`
- `connect()`
- `identify()`
- `read_settings()`
- `write_safe_setting()`
- `acquire()`
- `self_test()`
- `disconnect()`

Simulator devices:

1. `signal_source_01`
2. `scope_01`
3. `mux_01`
4. `temperature_01`

Fault injection must support deterministic scenario IDs:

- `CONNECTION_TIMEOUT`
- `STALE_RESOURCE`
- `WRONG_IDENTITY`
- `MUX_CHANNEL_SWAP`
- `CALIBRATION_SUPERSEDED`
- `TEMPERATURE_DRIFT`
- `NOISE_RISE`
- `SIGNAL_COLLAPSE`
- `TOOL_TIMEOUT`

Use seeded randomness or fixed traces so demo behavior does not vary.

Optional stretch adapter:
- PyVISA/SCPI for a local instrument.
- Never make this a dependency for judges to run the project.

---

# 13. CockroachDB integrations

## 13.1 Distributed Vector Index — mandatory runtime use

Requirements:
- Embeddings stored in CockroachDB `VECTOR` column.
- `CREATE VECTOR INDEX` migration included.
- Retrieval code demonstrably executes vector similarity queries.
- UI/debug panel exposes top-k memory hits, scores, status, and memory IDs.
- Tests verify relevant prior episode is retrieved.

## 13.2 Managed MCP Server — mandatory agent integration

Use the official managed endpoint:
- `https://cockroachlabs.cloud/mcp`

Local Codex development should use OAuth where possible.

Runtime agent should use a scoped service account/API key if MCP access from Lambda is implemented. Store the secret outside source control. Scope MCP to the single hackathon cluster.

The application should use MCP for a meaningful structured memory task, not a cosmetic health check. Preferred use:

- Agent requests structured experiment/device/memory context through MCP.
- Agent can write a low-risk memory/audit record through MCP when write consent is enabled.
- Direct psycopg remains allowed for deterministic application transactions and vector retrieval.

Log MCP tool name, purpose, success/failure, and latency at application level without logging credentials.

If runtime MCP proves blocked by an external platform limitation, do not fake it. Record the blocker in `STATUS.md`, preserve the verified local MCP integration, and keep vector indexing as the primary production memory path. However, the goal is real runtime MCP use before submission.

## 13.3 Optional ccloud CLI

If time permits, use ccloud for:
- provisioning/inspecting the hackathon cluster
- checking cluster state
- reading audit logs/metadata

Commit only scripts/commands, never credentials. This is bonus evidence, not a critical dependency.

## 13.4 Official CockroachDB Codex plugin

The project owner should install the official CockroachDB Codex plugin. Codex should use its skills for schema/query/security guidance. Do not vendor or modify upstream skills unless explicitly required.

---

# 14. AWS integration

## 14.1 Bedrock

Use the Bedrock Converse API or current recommended Bedrock runtime interface.

Do not hardcode a model ID in core logic. Use:
- `BEDROCK_MODEL_ID`
- `BEDROCK_EMBEDDING_MODEL_ID`

If the chosen embedding model has configurable dimensions, keep `EMBEDDING_DIM` consistent with the CockroachDB migration.

Do not build on Bedrock Agents Classic. Keep orchestration in our explicit state machine or use current AgentCore only if it clearly reduces complexity.

## 14.2 Lambda

Lambda hosts:
- API handlers
- agent step execution
- memory retrieval/consolidation
- simulator execution

Keep execution bounded. Long autonomous loops are not required.

## 14.3 S3

Store experiment artifacts such as:
- raw/synthetic waveform JSON or CSV
- run summary JSON
- generated plot image if useful

CockroachDB stores artifact metadata and hash; S3 stores the object.

## 14.4 Secrets

Preferred:
- Secrets Manager for DB URL and MCP service account token.

At minimum:
- encrypted Lambda environment variables / deployment secrets.

Never expose secrets to the browser.

---

# 15. API contract (minimal)

Suggested endpoints:

- `GET /health`
- `GET /devices`
- `POST /devices/{id}/connect`
- `POST /runs`
- `GET /runs/{id}`
- `POST /runs/{id}/step`
- `POST /runs/{id}/inject-fault`
- `GET /runs/{id}/timeline`
- `GET /runs/{id}/memories`
- `POST /actions/{id}/approve`
- `POST /actions/{id}/reject`
- `POST /runs/{id}/restart-demo`
- `GET /audit`

Every state-changing endpoint should be idempotent where practical.

---

# 16. UI requirements

Build one main dashboard with four zones.

## A. Experiment header

Show:
- run name/id
- status
- current step
- environment state
- “Restart Agent” demo control

## B. Device panel

Cards for each device:
- connected/disconnected/fault
- identity
- active calibration version
- last action

## C. Agent timeline

Chronological events:
- observed
- retrieved memory
- reasoned
- proposed action
- approval
- executed
- outcome
- memory written

Use concise human-readable text plus expandable structured JSON.

## D. Memory evidence drawer

For each retrieved memory show:
- memory title/id
- semantic similarity
- confidence
- status (`ACTIVE`, `SUPERSEDED`, etc.)
- source run
- prior action/outcome
- “Why this changed the decision”

Hero UI label:

> **Memory changed action**

This should appear when a prior failed/successful episode changes the chosen action compared with a no-memory baseline.

---

# 17. Seed/demo data

Create synthetic seed data covering:

- at least 20 normal/abnormal experiment episodes for functional tests
- the four hero scenarios
- enough varied memories to demonstrate non-trivial vector retrieval

If cost/time permits, create a benchmark dataset of roughly 200-1000 synthetic episodic memories. Be explicit in documentation that it is synthetic.

Never claim production scale that was not actually tested.

---

# 18. Evaluation suite

Implement deterministic evals; do not rely only on subjective screenshots.

## Eval 1 — Relevant memory retrieval

Given a current high-temperature/noise observation, expected prior intervention episode appears in top-k.

Metric:
- Recall@3 / pass-fail over curated cases.

## Eval 2 — Stale memory rejection

Given active calibration v2 and superseded v1, action uses v2.

Metric:
- 100% rejection of superseded value in current-action test cases.

## Eval 3 — Memory changes action

Run same scenario with memory retrieval disabled and enabled.

Expected:
- no-memory baseline attempts generic/failed sequence
- memory-enabled path selects previously successful recovery

Metric:
- action adaptation rate.

## Eval 4 — Restart continuity

Terminate/reinitialize agent after checkpoint.

Expected:
- resumes correct step
- no duplicate non-idempotent action

## Eval 5 — Unsafe action block

Prompt/tool output suggests out-of-policy write.

Expected:
- deterministic policy blocks or requests approval.

## Eval 6 — MCP failure recovery

Simulate MCP timeout.

Expected:
- bounded retry
- error is logged
- agent does not invent memory
- direct safe application state remains coherent

## Eval 7 — Tool result grounding

If device tool fails, agent must report failure rather than claiming success.

Create `evals/results.json` and a small human-readable summary.

---

# 19. Observability / evidence

Every agent decision should have a trace ID.

Log:
- request/run id
- agent step
- tool called
- selected memory IDs
- retrieval scores
- action selected
- policy decision
- result
- latency
- error type

Do not log:
- AWS secret keys
- DB passwords
- MCP bearer token
- full private prompts if they contain secrets

Add a demo-friendly audit/evidence panel.

---

# 20. Testing gates

No phase is complete until its gate passes.

Baseline commands should converge on something equivalent to:

```bash
pytest -q
ruff check .
mypy backend/app
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Tests must include:
- memory validity logic
- retrieval ranking
- action policy
- idempotent restart/checkpoint
- simulator fault cases
- database repository behavior
- API smoke tests

Cloud-only tests can be separately marked and skipped when credentials are absent, but local core tests must pass.

---

# 21. README narrative

README must answer in first screenful:

1. What is LabLedger?
2. Why does persistent memory matter?
3. What does CockroachDB uniquely do here?
4. What are the four hero scenarios?
5. How do I run the demo?

Must include:
- architecture diagram
- 60-second quick start
- screenshot/GIF if available
- CockroachDB tool usage table
- AWS service usage table
- eval results
- security/product-readiness notes
- synthetic-data disclosure
- license

Suggested central sentence:

> Traditional lab automation scripts know the current command. LabLedger remembers the previous failure, the recovery that worked, which calibration is still valid, and where a long-running experiment stopped.

---

# 22. Judging matrix

Maintain `docs/judging-matrix.md` with proof, not claims.

## Agentic Memory Design

Evidence:
- structured transactional state in CockroachDB
- episodic memory with vector embeddings
- action decisions store influencing memory IDs
- validity/supersession
- restart checkpoints
- memory-on vs memory-off behavior difference

## Technological Implementation

Evidence:
- distributed vector index migration + query
- managed MCP request evidence
- parameterized SQL
- safe scoped credentials
- tests

## Real-World Impact

Evidence:
- device connection troubleshooting
- calibration/version handover
- repeat-failure avoidance
- long-running experiment continuity

## Production Readiness

Evidence:
- approval/risk policy
- idempotency
- restart recovery
- audit trail
- scoped MCP access
- secret management
- MCP/tool failure behavior

## Creativity & Originality

Evidence:
- operational + scientific memory unified
- “memory has validity” rather than timeless RAG chunks
- experience/outcome memory changes actions without retraining

---

# 23. Demo requirements

The demo must be deterministic and under 3 minutes.

Target story:

1. 0:00-0:20 — “Labs forget operational experience.” Start current run.
2. 0:20-0:45 — Inject familiar signal/device anomaly.
3. 0:45-1:10 — Show CockroachDB vector retrieval of prior episode.
4. 1:10-1:30 — Show prior failed action and successful recovery; label “Memory changed action.”
5. 1:30-1:50 — Agent executes safe recovery and verifies improvement.
6. 1:50-2:10 — Show superseded calibration v1 vs active v2; agent uses v2.
7. 2:10-2:35 — Restart agent and resume from CockroachDB checkpoint.
8. 2:35-2:55 — Show architecture + CockroachDB MCP/vector + AWS services.
9. 2:55-3:00 — Tagline.

Do not waste demo time on signup, installation, or long chat typing.

---

# 24. Codex execution protocol

For each phase:

1. Read `AGENTS.md`, `TODO.md`, and current `STATUS.md`.
2. State the phase goal in `STATUS.md`.
3. Inspect existing code before editing.
4. Implement the smallest complete vertical slice.
5. Add/update tests in the same phase.
6. Run relevant checks.
7. Update `TODO.md` only when acceptance criteria actually pass.
8. Update `STATUS.md` with:
   - completed
   - tests run/results
   - files changed
   - blockers
   - next step
9. Commit logically if Git is available and requested.

Never:
- mark a task done without verification
- fabricate a successful cloud integration
- commit secrets
- delete user data
- use destructive SQL against a cloud cluster
- rewrite working modules unnecessarily

---

# 25. Definition of MVP complete

MVP is complete when all are true:

- [ ] App creates an experiment run.
- [ ] Simulator exposes at least four devices.
- [ ] Fault injection produces deterministic connection/signal faults.
- [ ] CockroachDB stores structured run/observation/action/outcome state.
- [ ] CockroachDB stores embeddings and has a vector index.
- [ ] Similar prior episode is retrieved in a hero scenario.
- [ ] Retrieved memory demonstrably changes agent action.
- [ ] Superseded calibration is rejected for current action.
- [ ] Agent restart resumes from checkpoint without duplicate action.
- [ ] Managed MCP Server is genuinely exercised and evidence captured.
- [ ] At least one AWS-hosted runtime path is functional.
- [ ] S3 artifact storage works or is clearly evidenced.
- [ ] Core tests/evals pass.
- [ ] Public demo URL works.
- [ ] README explains setup and architecture.
- [ ] Public repo has LICENSE.
- [ ] Demo video is under 3 minutes and shows the memory layer.

Anything beyond this is polish.
