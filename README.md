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
memory access path for the agent. These integrations are not yet implemented in
P0.

## Hero scenarios

1. A recovered device connection failure becomes reusable operational memory.
2. A prior intervention outcome changes the action selected in a later run.
3. A superseded calibration remains visible as history but cannot drive a
   current action.
4. A restarted agent resumes from its latest checkpoint without duplicating a
   completed risky action.

## Current status

P0 establishes repository, licensing, configuration, and account readiness.
Application code begins in P1 only after the P0 gate is satisfied. See
[`STATUS.md`](STATUS.md) for verified progress and blockers.

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
