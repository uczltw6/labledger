# LabLedger Hackathon TODO

**Today:** 7 Aug 2026 (Europe/London)
**Submission deadline:** 18 Aug 2026, 22:00 Europe/London
**Strategy:** finish CockroachDB MVP early enough to leave protected time for the Arm challenge. Target feature freeze: **12 Aug**.

Legend:
- `[ ]` not started
- `[-]` in progress
- `[x]` verified complete
- `[!]` blocked / user action required

Never mark `[x]` unless the acceptance gate passes.

---

# P0 — Scope, accounts, repo, compliance | 7 Aug

## Tasks
- [x] Create GitHub repo `labledger` (or final chosen name).
- [x] Add MIT or Apache-2.0 `LICENSE`.
- [x] Commit `AGENTS.md`, `TODO.md`, `RUNBOOK.md`.
- [x] Add `.gitignore` for Python, Node, `.env`, AWS/SAM, test artifacts.
- [x] Create `.env.example` with placeholders only.
- [x] Create `README.md` skeleton.
- [x] Create `STATUS.md`.
- [!] Register/start Devpost submission now so all form fields are visible.
- [!] Create CockroachDB Cloud account/cluster.
- [!] Create/verify AWS account and a development IAM identity.
- [!] Confirm selected AWS region supports chosen Bedrock model(s).

## Gate P0

Pass only if:
- public repo exists
- license visible
- no secrets in git
- Codex can read AGENTS/TODO
- CockroachDB cluster exists
- AWS CLI identity check works or exact blocker documented

P0 status: **BLOCKED — USER ACTION REQUIRED.** The public repository and all
local compliance checks pass. The Devpost, CockroachDB Cloud, and AWS account
steps are documented in `STATUS.md`; P1 has not started.

---

# P1 — Local deterministic lab simulator | 7-8 Aug

## Tasks
- [ ] Create Python project/package skeleton.
- [ ] Define `DeviceAdapter` interface.
- [ ] Implement `signal_source_01` simulator.
- [ ] Implement `scope_01` simulator.
- [ ] Implement `mux_01` simulator.
- [ ] Implement `temperature_01` simulator.
- [ ] Implement deterministic seeded fault injection.
- [ ] Implement scenario A connection failure.
- [ ] Implement scenario B temperature/noise/signal anomaly.
- [ ] Unit-test all fault transitions.

## Gate P1

One command can run a deterministic scenario and output:
- observation
- attempted action
- outcome
- stable scenario ID

No LLM required yet.

---

# P2 — CockroachDB structured memory | 8 Aug

## Tasks
- [ ] Implement schema migrations.
- [ ] Create devices/runs/observations/actions/outcomes/calibrations/memories/checkpoints/artifacts/audit tables.
- [ ] Implement repository layer with parameterized SQL.
- [ ] Create transactions for action + outcome + checkpoint consistency.
- [ ] Seed hero scenarios.
- [ ] Add integration tests against CockroachDB when credentials exist.
- [ ] Add local mocks/fakes for credential-free tests.

## Gate P2

Run a scenario, kill/restart local process, reload the run and latest checkpoint from CockroachDB.

---

# P3 — Vector memory and validity | 8-9 Aug

## Tasks
- [ ] Choose embedding model and dimension.
- [ ] Add embedding generation abstraction.
- [ ] Add `VECTOR(dim)` field.
- [ ] Create CockroachDB vector index.
- [ ] Implement ANN retrieval.
- [ ] Implement validity filter: active/superseded/expired/disputed.
- [ ] Implement deterministic reranking.
- [ ] Persist influencing memory IDs on actions.
- [ ] Seed prior failed/successful intervention memory.
- [ ] Seed v1/v2 calibration conflict.
- [ ] Implement top-k retrieval evidence response.

## Gate P3

Automated tests prove:
- expected prior episode in top-3
- superseded calibration never drives a current action

---

# P4 — Bedrock reasoning + explicit agent state machine | 9 Aug

## Tasks
- [ ] Implement Bedrock client with model ID from env.
- [ ] Implement structured prompt/output contract.
- [ ] Implement state machine:
  OBSERVE -> RETRIEVE -> DIAGNOSE -> PROPOSE -> POLICY -> EXECUTE -> VERIFY -> MEMORY -> CHECKPOINT.
- [ ] Deterministic code validates model-selected tools/actions.
- [ ] Add retry/timeouts.
- [ ] Add grounding rule: tool failure cannot become claimed success.
- [ ] Implement memory-on / memory-off run mode for eval/demo.

## Gate P4

Same input produces a materially better/different action path with prior successful memory enabled.

---

# P5 — CockroachDB Managed MCP | 9-10 Aug

## Tasks
- [ ] Install official CockroachDB Codex plugin locally.
- [ ] Connect Codex to CockroachDB Cloud Managed MCP via OAuth.
- [ ] Scope MCP connection to the hackathon cluster.
- [ ] Verify schema/table read through MCP.
- [ ] Create scoped service account for runtime MCP if feasible.
- [ ] Store runtime MCP secret outside repo.
- [ ] Implement MCP client path from the agent/Lambda.
- [ ] Use MCP for a meaningful structured memory operation.
- [ ] Capture tool-call evidence without exposing credentials.
- [ ] Test MCP timeout/failure behavior.

## Gate P5

Evidence shows a real MCP call tied to a LabLedger agent memory operation.

---

# P6 — UI / demo experience | 10-11 Aug

## Tasks
- [ ] Create Vite/React frontend.
- [ ] Experiment header/status.
- [ ] Device cards.
- [ ] Agent event timeline.
- [ ] Memory evidence drawer.
- [ ] ACTIVE/SUPERSEDED badges.
- [ ] “Memory changed action” hero indicator.
- [ ] Fault injection demo controls.
- [ ] Restart Agent control.
- [ ] Approval control for medium-risk action.
- [ ] No-memory baseline toggle only if visually clear.

## Gate P6

A first-time viewer can understand within ~15 seconds:
- what failed
- what memory was retrieved
- how it changed the action
- whether the action worked

---

# P7 — AWS deployment | 11-12 Aug

## Tasks
- [ ] Create SAM/infra template for Lambda + API Gateway.
- [ ] Configure S3 artifact bucket.
- [ ] Deploy backend.
- [ ] Build frontend.
- [ ] Deploy frontend to S3/CloudFront or another clearly AWS-hosted path.
- [ ] Configure CORS.
- [ ] Configure secrets safely.
- [ ] Run cloud smoke test.
- [ ] Verify public demo URL from incognito browser.

## Gate P7

Public URL works without local machine running and can complete at least hero scenario B.

---

# P8 — Product readiness and failure handling | 11-12 Aug

## Tasks
- [ ] Risk/approval policy tests.
- [ ] Idempotency tests.
- [ ] Restart continuity test.
- [ ] MCP failure test.
- [ ] Bedrock timeout/failure test.
- [ ] Cockroach transient retry behavior where appropriate.
- [ ] Audit event trace IDs.
- [ ] Secret scan.
- [ ] Dependency/security sanity check.

## Gate P8

All high-value failure tests pass; failures are explicit rather than silently swallowed.

---

# P9 — Evals and benchmark | 12 Aug

## Tasks
- [ ] Curate >= 10 retrieval cases.
- [ ] Run Recall@3.
- [ ] Run stale-memory rejection eval.
- [ ] Run action-adaptation eval.
- [ ] Run restart eval.
- [ ] Run unsafe-action eval.
- [ ] Save machine-readable `evals/results.json`.
- [ ] Generate concise README summary.
- [ ] Optional: seed 200-1000 synthetic memories and measure retrieval latency.

## Gate P9

Evaluation results are reproducible with one documented command.

---

# P10 — Repo and judge-facing evidence | 12-13 Aug

## Tasks
- [ ] Finish README first screenful.
- [ ] Add architecture diagram.
- [ ] Add CockroachDB tools table.
- [ ] Add AWS services table.
- [ ] Add evaluation results.
- [ ] Add synthetic-data disclosure.
- [ ] Add security/product-readiness section.
- [ ] Add setup/run instructions from clean environment.
- [ ] Add screenshots/GIF.
- [ ] Complete `docs/judging-matrix.md` with evidence links.
- [ ] Run `scripts/verify_submission`.

## Gate P10

A clean-room reviewer can understand and run the project from README without private explanation.

---

# Protected Arm window | 14-15 Aug

CockroachDB work during this window should be limited to:
- critical bug fixes
- keeping deployment alive
- small documentation fixes

Do not start new CockroachDB features unless MVP is broken.

---

# P11 — Video + Devpost | 16 Aug

## Tasks
- [ ] Freeze demo seed/scenario.
- [ ] Write <3 min script.
- [ ] Rehearse twice.
- [ ] Record deterministic demo.
- [ ] Show vector memory retrieval clearly.
- [ ] Show MCP evidence clearly but do not expose secrets.
- [ ] Show restart continuity.
- [ ] Show architecture/AWS deployment.
- [ ] Upload public YouTube/Vimeo.
- [ ] Complete Devpost draft.

## Gate P11

Video is <3 min and a viewer can identify: CockroachDB persistent memory, action change, AWS usage.

---

# P12 — Final clean-room + submit | 17 Aug

## Tasks
- [ ] Clone repo into clean directory/machine.
- [ ] Follow README exactly.
- [ ] Verify license visible on GitHub.
- [ ] Verify no secrets/history accidents.
- [ ] Verify public demo URL.
- [ ] Verify video URL public.
- [ ] Verify repo URL public.
- [ ] Verify CockroachDB tool descriptions accurate.
- [ ] Verify AWS service descriptions accurate.
- [ ] Submit Devpost.
- [ ] Save confirmation screenshot.

---

# Buffer | 18 Aug

Use only for:
- submission metadata corrections
- deployment outage
- broken public link
- last critical compliance issue

Do not rely on this day for core development.
