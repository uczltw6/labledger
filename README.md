# LabLedger

**Persistent Memory for Autonomous LabOps**

LabLedger is an AI lab-operations agent that will remember device state,
connection failures, calibration changes, experiment observations,
interventions, and outcomes, then use that evidence to make safer decisions in
future runs.

Traditional lab automation scripts know the current command. LabLedger is
designed to remember the previous failure, the recovery that worked, which
calibration is still valid, and where a long-running experiment stopped.

## Why CockroachDB

The architecture keeps structured operational state and semantic episodic
memory in one durable CockroachDB system of record. Distributed Vector Indexing
now retrieves related prior episodes, while deterministic validity, confidence,
device-context, and outcome rules determine whether a memory is eligible to
influence a future action. The CockroachDB Cloud Managed MCP Server remains a
planned meaningful structured-memory access path for a later phase.

## Hero scenarios

1. A recovered device connection failure becomes reusable operational memory.
2. A prior intervention outcome changes the action selected in a later run.
3. A superseded calibration remains visible as history but cannot drive a
   current action.
4. A restarted agent resumes from its latest checkpoint without duplicating a
   completed risky action.

## Current status

P0 established repository, licensing, configuration, and account readiness.
P1 provides the local deterministic four-device simulator and Scenario A/B
foundations. P2 now includes the structured-memory mapping, repository,
transaction, migration, and restart-verifier paths, and its real CockroachDB
process-boundary gate has been verified. P3 adds production Bedrock embeddings,
real CockroachDB `VECTOR(512)` storage and cosine indexing, deterministic
reranking, and separate semantic relevance/current-truth policy. Its live Gate
A/B evidence passes. Rerunning live checks requires local credentials. See
[`STATUS.md`](STATUS.md) for verified progress and blockers.

## Local deterministic simulator

Python 3.12 is required. From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m backend.app.devices.simulator --scenario all --json
```

The final command runs both stable P1 scenarios and emits observations,
attempted actions, outcomes, step order, seed, and stable scenario IDs as JSON.
It has no network, database, AWS, Bedrock, MCP, frontend, or LLM dependency.

Run the scenarios individually with `--scenario scenario-a` or
`--scenario scenario-b`. Supply `--seed <integer>` to reproduce a specific
configuration.

## P2 structured-memory verification

Run the credential-free P2 checks on Windows:

```powershell
.\.venv\Scripts\python scripts\verify_p2.py --local
```

This validates the non-destructive 11-table migration, strict trace-to-row
mapping, explicit simulator checkpoint snapshots, conflict-safe idempotency,
cross-record invariants, and copy-on-write fake. It does not satisfy Gate P2.
For the real gate on Windows, first download the cluster's public CA certificate
from the Cloud **Connect** instructions while keeping `sslmode=verify-full`:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\postgresql" | Out-Null
Invoke-WebRequest `
  -Uri "https://cockroachlabs.cloud/clusters/<cluster-id>/cert" `
  -OutFile "$env:APPDATA\postgresql\root.crt"
```

Put the complete `postgresql://...` URL—not the password by itself—only in the
ignored `.env` file as `COCKROACH_DATABASE_URL`, then run:

```powershell
.\.venv\Scripts\python scripts\verify_p2.py
```

The verifier applies only idempotent schema creation and synthetic inserts,
then proves that Process A can persist and exit and a fresh Process B can load
the run, latest checkpoint, ordered timeline, and failed-action evidence. The
P2 baseline migration intentionally remains free of vector definitions; P3 adds
them through the separate additive `002_vector_memory.sql` migration.
The verifier rejects password-only values, unresolved password placeholders,
non-`verify-full` Cloud URLs, and a missing Windows CA with secret-safe errors.

## P3 vector-memory verification

The credential-free contract check uses an explicitly TEST-ONLY provider and
cannot satisfy Gate P3:

```powershell
.\.venv\Scripts\python scripts\verify_p3.py --local
```

For the real gate, keep the complete database URL only in ignored `.env`, log
the AWS CLI into the intended account, and set the non-secret runtime choices:

```powershell
$env:AWS_REGION = "eu-west-2"
$env:BEDROCK_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
$env:EMBEDDING_DIM = "512"
.\.venv\Scripts\python scripts\verify_p3.py
```

The live verifier checks account-visible model availability, performs a real
Bedrock invocation, applies the repeatable vector migration, persists grounded
episodic memories, executes cosine top-k search in CockroachDB, and enforces
calibration validity. It generates non-secret judge evidence at
[`docs/evidence/p3-vector-memory.json`](docs/evidence/p3-vector-memory.json).

## P0 verification

From the repository root:

```powershell
python scripts/verify_p0.py
```

The script checks the local repository skeleton, placeholder-only example
configuration, tracked-file hygiene, and public GitHub visibility. AWS and
CockroachDB readiness are reported separately in `STATUS.md` until their
account-level checks can be completed.

## Data and security

All demo data will be synthetic. Secrets, private instrument addresses, and
employer-confidential information must never be committed. Copy
`.env.example` to an ignored `.env` file for local credentials.

## License

LabLedger is licensed under the [MIT License](LICENSE).
