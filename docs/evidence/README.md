# Generated evidence

`scripts/verify_p3.py` writes `p3-vector-memory.json` only after the production
Bedrock invocation, CockroachDB migration/index verification, live top-k query,
and calibration-validity gate all pass.

The generated artifact contains synthetic memory/run identifiers, retrieval
scores, model metadata, and non-secret schema/index evidence. It must never
contain an AWS identity, database connection URL, password, access key, account
ID, ARN, cluster identifier, or token.
