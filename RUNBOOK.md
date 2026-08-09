# LabLedger Operator Runbook

This is the human-facing guide for building LabLedger with Codex safely and efficiently.

---

# 1. What you are building

You are not building a lab chatbot.

You are building a long-running agent that can:

1. manage a simulated set of laboratory instruments
2. record experimental and operational events
3. remember connection faults and recoveries
4. remember failed/successful interventions
5. track which calibration is still valid
6. retrieve relevant prior episodes semantically
7. change a future action based on those memories
8. survive an agent restart and resume safely
9. store raw experiment artifacts in AWS S3
10. expose enough evidence that a judge can see CockroachDB doing real memory work

The public demo uses synthetic data. A later portfolio version may connect to real instruments through PyVISA/SCPI.

---

# 2. Accounts / prerequisites

Have ready:

- GitHub account
- Devpost account
- CockroachDB Cloud account
- AWS account
- Codex CLI
- Git
- Python 3.12 (or supported equivalent)
- Node.js LTS
- AWS CLI
- optional: ccloud CLI

Do not paste secrets into Codex chat if they can instead be stored in environment variables or local configuration.

---

# 3. Create the repo

Recommended repo name:

```text
labledger
```

Alternative names if unavailable:

```text
labledger-ai
labops-memory
experiment-memory-agent
```

Initialize with:

- README
- MIT license
- Python `.gitignore`

Then copy these files to repo root:

- `AGENTS.md`
- `TODO.md`
- `RUNBOOK.md`

Create `STATUS.md` with:

```md
# STATUS

Current phase: P0
State: NOT STARTED

## Completed
- None

## Verification
- None

## Blockers
- None

## Next
- Bootstrap repo and verify cloud prerequisites.
```

---

# 4. Install CockroachDB’s official Codex plugin

Current official install flow:

```bash
codex plugin marketplace add cockroachdb/codex-plugin
codex plugin add cockroachdb@cockroachdb-codex-plugin
```

On first use, Codex may ask you to review/trust the plugin’s safety hooks. Review them, then approve if the displayed paths match the official plugin payload.

The plugin provides CockroachDB skills and MCP integrations. It should help Codex avoid common schema/SQL anti-patterns.

---

# 5. Connect Codex to CockroachDB Managed MCP

## Recommended local-development path: OAuth

Add the MCP server:

```bash
codex mcp add cockroachdb-cloud --url https://cockroachlabs.cloud/mcp
```

Then authenticate:

```bash
codex mcp login cockroachdb-cloud
```

A browser opens. Select the correct CockroachDB organization and authorize access.

Initially prefer read-only access while validating the connection.

## Scope to one cluster

For the hackathon, avoid giving the AI tool access to unrelated clusters. Scope the MCP connection to the LabLedger cluster.

CockroachDB supports an `mcp-cluster-id` header. Follow the current Cloud Console/docs flow to add the selected cluster ID.

## Runtime service-account path

If the AWS Lambda agent will call Managed MCP directly:

1. Create a dedicated CockroachDB service account.
2. Give it only the permissions needed for the LabLedger cluster.
3. Generate its API key.
4. Use the Managed MCP endpoint with headers:
   - `mcp-cluster-id`
   - `Authorization: Bearer <service-account-api-key>`
5. Put that secret in AWS Secrets Manager or equivalent secret storage.
6. Never put it in `.env.example`, README screenshots, logs, or frontend code.

---

# 6. CockroachDB cluster setup

Fast path:

1. Create a CockroachDB Cloud Basic cluster in an AWS region that is convenient for your Lambda deployment.
2. Name it clearly, e.g. `labledger-hackathon`.
3. Create application DB user/credentials.
4. On Windows, download the cluster's public CA certificate without weakening
   `sslmode=verify-full`:

   ```powershell
   New-Item -ItemType Directory -Force "$env:APPDATA\postgresql" | Out-Null
   Invoke-WebRequest `
     -Uri "https://cockroachlabs.cloud/clusters/<cluster-id>/cert" `
     -OutFile "$env:APPDATA\postgresql\root.crt"
   ```

5. Copy the complete `postgresql://...` connection URL—not only its password—
   into the ignored local `.env` secret store.
6. Test the connection while keeping certificate and hostname verification
   enabled.
7. Keep the cluster isolated from any non-hackathon data.

Optional ccloud path:

```bash
ccloud auth login
```

Then inspect available commands before creation; do not blindly paste destructive commands. If ccloud is used, preserve command scripts as evidence of the third CockroachDB tool.

---

# 7. AWS setup

## Region

Choose one region and keep Lambda/S3/Bedrock close together where possible.

Before coding against a specific Bedrock model, verify the model is available to your account/region.

## IAM

Create/choose a development identity with only needed permissions.

For deployed Lambda, create a role that can:

- invoke the chosen Bedrock model
- read/write the specific LabLedger S3 bucket
- read the specific LabLedger secrets
- write CloudWatch logs

Avoid broad administrator permissions for the deployed app.

## S3

Create a bucket for demo artifacts, e.g.:

```text
labledger-demo-artifacts-<unique-suffix>
```

Keep public access blocked unless a specific public artifact is intentionally required. The web app should access data via the backend or signed URLs.

---

# 8. Local environment variables

Create `.env` locally. Never commit it.

Suggested variables:

```text
APP_ENV=dev
AWS_REGION=<region>
BEDROCK_MODEL_ID=<current-model-id>
BEDROCK_EMBEDDING_MODEL_ID=<embedding-model-id>
EMBEDDING_DIM=<dimension>
COCKROACH_DATABASE_URL=<secret>
COCKROACHDB_CLUSTER_ID=<cluster-id>
COCKROACH_MCP_URL=https://cockroachlabs.cloud/mcp
COCKROACH_MCP_API_KEY=<runtime-only-secret-if-used>
S3_BUCKET=<bucket>
FRONTEND_ORIGIN=http://localhost:5173
```

`.env.example` must contain placeholders, never real values.

---

# 9. First Codex invocation

Start Codex from the repository root.

Paste this instruction:

```text
Read AGENTS.md, TODO.md, RUNBOOK.md, and STATUS.md in full before changing anything.
We are building LabLedger for the CockroachDB × AWS Agentic Memory Hackathon.
Execute P0 only.
Inspect the environment first, create the minimum repo skeleton required by P0, add verification scripts/tests where appropriate, and do not move to P1 until P0 acceptance criteria are actually satisfied.
Never commit or print secrets. Do not use destructive CockroachDB commands.
If a credential or browser/cloud-console action is required, record it under NEEDS_USER_ACTION in STATUS.md with exact instructions, then continue any independent work.
At the end, run the P0 checks, update STATUS.md and TODO.md truthfully, and summarize files changed and commands/tests run.
```

Do not tell Codex “build the entire app” in one shot. Use phase gates.

---

# 10. Phase-by-phase Codex prompts

After you manually inspect the previous phase, use one prompt per phase.

## P1

```text
Read AGENTS.md/TODO.md/STATUS.md. Execute P1 only: build the deterministic device simulator and fault injection system. No LLM and no cloud dependency in core simulator tests. Implement the smallest clean abstraction that can later support PyVISA. Add unit tests for all required fault transitions. Run tests and update status/todo only if the P1 gate passes.
```

## P2

```text
Execute P2 only. Implement the CockroachDB structured memory schema and repository layer from AGENTS.md. Use CockroachDB-safe schema patterns, parameterized SQL, and transactions for action/outcome/checkpoint consistency. Use the official CockroachDB Codex skills where relevant. Add migrations and integration tests. Do not add vector search yet except placeholders needed for the next migration.
```

## P3

```text
Execute P3 only. Add real CockroachDB VECTOR storage/indexing, embedding abstraction, semantic retrieval, validity filtering, and deterministic reranking. Implement the superseded calibration test and top-k prior episode retrieval. Prove the expected episode is in top-3 and stale calibration cannot drive current action. Capture query/evidence needed for the demo.
```

Verified P3 local and live entry points:

```powershell
.\.venv\Scripts\python scripts\verify_p3.py --local
$env:AWS_REGION = "eu-west-2"
$env:BEDROCK_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
$env:EMBEDDING_DIM = "512"
.\.venv\Scripts\python scripts\verify_p3.py
```

The live command requires the ignored `COCKROACH_DATABASE_URL` and an
authenticated AWS CLI session. It writes only non-secret evidence to
`docs/evidence/p3-vector-memory.json`.

## P4

```text
Execute P4 only. Add Bedrock model invocation behind an interface and implement the explicit agent state machine in AGENTS.md. Deterministic code must control policy, idempotency, validity filtering, and writes. Add memory-enabled versus memory-disabled evaluation mode. Never allow model text to directly execute arbitrary commands.
```

## P5

```text
Execute P5 only. Integrate the CockroachDB Cloud Managed MCP Server meaningfully. First verify the existing local Codex MCP connection. Then implement/test the application MCP client path if credentials are available, using a single-cluster scoped service account for runtime. Use MCP for a real structured memory/context operation, not a cosmetic ping. Add failure handling and evidence logging without secrets.
```

## P6

```text
Execute P6 only. Build the smallest polished React/Vite judge-facing UI: experiment status, device cards, agent timeline, memory evidence drawer, ACTIVE/SUPERSEDED state, Memory changed action indicator, fault injection, approval, and restart demo. Optimize for a <3-minute demo, not a general-purpose product dashboard.
```

## P7/P8

```text
Execute P7 and then P8, one gate at a time. Deploy the functional app on AWS using the simplest maintainable path in AGENTS.md. Then add failure handling, idempotency, approvals, audit evidence, and secret checks. Never mark deployment complete until the public URL works from an incognito browser without the local machine.
```

## P9/P10

```text
Execute P9 and P10. Build reproducible evals and judge-facing evidence. Then finish README, architecture, judging matrix, setup instructions, synthetic-data disclosure, screenshots, and submission verification. Make claims only when backed by code/tests/evidence.
```

---

# 11. What you should manually check after every Codex phase

Do not rely only on Codex’s “done” statement.

Check:

1. `git diff`
2. new dependencies
3. `.env`/secrets are not staged
4. `STATUS.md` contains actual test output summary
5. tests really exist for the claimed feature
6. no fake hard-coded “successful” agent result
7. no cloud service is claimed if it was only mocked
8. README statements match current implementation

Useful commands:

```bash
git status
git diff --stat
git diff
```

Then run the test commands from the repo.

---

# 12. Memory demo data you should ask Codex to seed

Use synthetic data inspired by realistic instrument workflows.

## Seed Episode 1 — connection recovery

Observation:
- scope connection timeout
- stale resource/address hint

Failed action:
- immediate repeated reconnect

Successful sequence:
- rediscover resources
- identify candidate device
- verify identity
- reconnect

Long-term lesson:
- after repeated timeout, rediscover and verify identity before retrying the same resource string.

## Seed Episode 2 — experimental intervention

Observation:
- temperature elevated
- noise increased
- signal quality fell

Failed action:
- Calibration A

Successful action:
- reduce drive amplitude 10%

Outcome:
- noise decreases
- signal quality recovers

## Seed Episode 3 — calibration validity

v1:
- gain 4.2
- superseded

v2:
- gain 3.8
- active

Semantic search may return both, but current action must use v2.

## Seed Episode 4 — MUX mapping

Observation:
- unexpected channel signature

Recovery:
- verify mapping before modifying it
- medium-risk mapping change requires approval

Keep all values explicitly synthetic.

---

# 13. The single most important eval

Ask Codex to make this impossible to fake:

**Run the identical scenario twice.**

A. `memory_enabled=false`
- agent has current observation only

B. `memory_enabled=true`
- agent retrieves prior failed/successful episode

The result should show a different action selection or action ordering, and the memory-enabled route should avoid repeating the previously failed step.

Store both traces and display them in the demo/eval output.

This proves memory is functional, not decorative.

---

# 14. When to use a real instrument

Only after MVP and cloud demo are stable.

Optional portfolio enhancement:

- Add a PyVISA adapter.
- Connect one harmless read-only instrument locally.
- Demonstrate `discover -> identify -> read settings -> acquire`.
- Never expose private lab network/resource identifiers in the public repo/video.
- Keep the simulator as the judge-runnable default.

A real-instrument clip can strengthen authenticity, but it is lower priority than a reliable memory demo.

---

# 15. Product story for interviews / Devpost

Use a story that truthfully connects academic and industrial experience without leaking employer data:

> Experimental systems fail in ways that rarely make it into the final dataset: instruments disappear from the bus, resource addresses go stale, channels are misconfigured, calibrations change, and a recovery that worked once can live only in one engineer’s memory. The same issue appears in long academic experiments and industrial sensing systems. LabLedger turns those operational episodes and experimental outcomes into durable agent memory, so the next run can reuse evidence instead of repeating the same failure.

Then explain the technical insight:

> We store structured device/run state and semantic episodic memory in the same CockroachDB system of record. A prior failure is not just retrieved as text: its validity, confidence, action, and outcome are checked before it can influence a new action.

---

# 16. 3-minute demo operating procedure

Before recording:

1. Seed known memories.
2. Verify demo URL.
3. Open dashboard with no irrelevant tabs.
4. Clear unrelated logs.
5. Confirm no credentials can appear.
6. Run the hero scenario once.
7. Reset to deterministic starting state.
8. Record.

Demo sequence:

1. Start Run 028.
2. Inject familiar temperature/noise anomaly or connection fault.
3. Show retrieved prior memory and score.
4. Expand the prior memory: failed action + successful recovery.
5. Show “Memory changed action.”
6. Execute safe action and show verified improvement.
7. Show active vs superseded calibration.
8. Restart agent; show persisted run/checkpoint resumes.
9. Show architecture/CockroachDB/AWS evidence.
10. End with tagline.

Do not spend time narrating every table.

---

# 17. Submission checklist

The current challenge requires a public open-source repo, functional demo app URL, and a public video under 3 minutes. It also asks entrants to identify which CockroachDB tools and AWS services were used and how.

Before submission verify:

- [ ] GitHub repo public
- [ ] LICENSE visible
- [ ] README complete
- [ ] dependencies/setup instructions complete
- [ ] example config/data present
- [ ] demo URL public
- [ ] video public and <3 minutes
- [ ] CockroachDB Distributed Vector Index usage described with evidence
- [ ] Managed MCP usage described with evidence
- [ ] AWS Bedrock/Lambda/S3 usage described accurately
- [ ] architecture diagram included
- [ ] no secrets
- [ ] no confidential employer data
- [ ] eval results reproducible
- [ ] Devpost draft started before final day

---

# 18. Useful official references

CockroachDB × AWS challenge:
https://cockroachdb-ai.devpost.com/

Challenge rules:
https://cockroachdb-ai.devpost.com/rules

CockroachDB Managed MCP docs:
https://www.cockroachlabs.com/docs/cockroachcloud/connect-to-the-cockroachdb-cloud-mcp-server

CockroachDB vector indexes:
https://www.cockroachlabs.com/docs/stable/vector-indexes.html

CockroachDB official Codex plugin:
https://github.com/cockroachdb/codex-plugin

CockroachDB AI overview:
https://www.cockroachlabs.com/product/ai/

Amazon Bedrock AgentCore overview:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html

---

# 19. Final rule

When in doubt, optimize for the judge seeing this chain clearly:

```text
Realistic lab failure
  -> persistent CockroachDB memory
  -> semantic + structured retrieval
  -> validity/confidence check
  -> different agent decision
  -> safe tool action
  -> measured outcome
  -> new memory
  -> restart and continue
```

That chain is the product.
