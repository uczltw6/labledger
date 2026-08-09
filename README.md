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

The planned architecture keeps structured operational state and semantic
episodic memory in one durable CockroachDB system of record. Distributed Vector
Indexing will retrieve related prior episodes, while validity, confidence, and
outcome metadata will determine whether a memory may influence a new action.
The CockroachDB Cloud Managed MCP Server is planned as a meaningful structured
memory access path for the agent. These integrations are not implemented in the
P1 simulator.

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
process-boundary gate has been verified. Rerunning the live checks still
requires local credentials. See
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
the run, latest checkpoint, ordered timeline, and failed-action evidence. P3
will add vector storage and indexing; they are intentionally absent from P2.
The verifier rejects password-only values, unresolved password placeholders,
non-`verify-full` Cloud URLs, and a missing Windows CA with secret-safe errors.

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
