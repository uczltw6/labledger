# STATUS

Current phase: P0 — Scope, accounts, repo, compliance
State: BLOCKED — USER ACTION REQUIRED

## Phase goal

Establish the public repository and local compliance skeleton, verify that no
secrets are tracked, and document any account or cloud prerequisites that
cannot be completed safely from this environment.

## Completed

- Read `AGENTS.md`, `TODO.md`, and `RUNBOOK.md` in full.
- Confirmed that `STATUS.md` was absent and created it for P0 tracking.
- Inspected the repository, runtimes, CLI availability, and configuration
  presence without reading or displaying credential values.
- Created the public repository <https://github.com/uczltw6/labledger> with
  `main` as its default branch.
- Added the MIT license; GitHub reports SPDX identifier `MIT`.
- Committed and pushed `AGENTS.md`, `TODO.md`, `RUNBOOK.md`, and the local P0
  compliance skeleton.
- Added Python/Node/environment/AWS-SAM/test-artifact ignore rules.
- Added `.env.example` with explicit placeholders only.
- Added the P0 README skeleton and dependency-free repository verifier.
- Kept P1 application/package work out of scope.

## Verification

- `python scripts/verify_p0.py` — PASS, 7/7 checks:
  required files, MIT text, placeholder-only `.env.example`, ignore coverage,
  required tracked files, tracked-secret scan, and public GitHub visibility.
- `python -m py_compile scripts/verify_p0.py` — PASS.
- `git diff --cached --check` before the initial commit — PASS after whitespace cleanup.
- `gh repo view --json nameWithOwner,isPrivate,defaultBranchRef` — public
  repository confirmed; default branch `main`.
- `gh api 'repos/{owner}/{repo}/license' --jq '.license.spdx_id'` — `MIT`.
- Remote `main` contains `AGENTS.md`, `TODO.md`, `RUNBOOK.md`, `LICENSE`, and
  `README.md`.
- Environment findings: Git 2.45.1, Python 3.11.5, Node 24.15.0, npm 11.12.1,
  GitHub CLI 2.91.0. AWS CLI, ccloud, CockroachDB CLI, Python 3.12, AWS profile,
  and project cloud environment variables are not present.

## NEEDS_USER_ACTION

### 1. Start the Devpost draft

1. Open the [hackathon page](https://cockroachdb-ai.devpost.com/) and sign in.
2. Click **Join hackathon**, review/accept the official rules, then open
   **My projects**.
3. Start a draft named **LabLedger** so every required submission field is
   visible; save it, but do not submit yet.
4. Report only that the draft exists. Do not paste private account details.

### 2. Create and verify the CockroachDB Cloud cluster

1. Sign in to [CockroachDB Cloud](https://cockroachlabs.cloud/), select the
   intended organization, and create a **Basic** cluster following the
   [official Basic-cluster guide](https://www.cockroachlabs.com/docs/cockroachcloud/create-a-basic-cluster).
2. Select **AWS**, use the same region selected for the application where
   available, choose **Start for free** only after reviewing the displayed
   limits/costs, and name it `labledger-hackathon`.
3. Create a dedicated SQL user, store its password in a password manager, and
   restrict network authorization to the current development IP instead of
   leaving `0.0.0.0/0` when practical.
4. Copy `.env.example` to the ignored `.env` file and populate only
   `COCKROACH_DATABASE_URL` and `COCKROACHDB_CLUSTER_ID` there. Never paste or
   commit the connection string.
5. From the cluster's **Connect** dialog, install the CockroachDB SQL client and
   load the ignored `.env` value into the current process without printing it,
   then run this read-only verification locally:

   ```powershell
   $dbLine = Get-Content -LiteralPath .env | Where-Object { $_.StartsWith('COCKROACH_DATABASE_URL=') } | Select-Object -First 1
   if (-not $dbLine) { throw 'COCKROACH_DATABASE_URL is missing from .env' }
   $env:COCKROACH_DATABASE_URL = $dbLine.Substring($dbLine.IndexOf('=') + 1)
   try {
     cockroach sql --url $env:COCKROACH_DATABASE_URL --execute "SELECT current_database(), version();"
   } finally {
     Remove-Item Env:COCKROACH_DATABASE_URL -ErrorAction SilentlyContinue
   }
   ```

6. Report only that the query succeeded plus the non-secret cloud/region and
   cluster name. Do not report the URL, password, or cluster UUID.

### 3. Configure and verify the AWS development identity and Bedrock region

1. Install AWS CLI v2, then open a new PowerShell session:

   ```powershell
   winget install --id Amazon.AWSCLI --exact
   aws --version
   ```

2. In the AWS account, create or select a least-privilege development identity
   (IAM Identity Center/SSO is preferred), then configure it locally:

   ```powershell
   aws configure sso --profile labledger-dev
   ```

3. Verify the identity without copying its account number or ARN into the repo:

   ```powershell
   aws sts get-caller-identity --profile labledger-dev *> $null
   if ($LASTEXITCODE -eq 0) { Write-Output "AWS identity verified" }
   ```

4. Choose one region (start with `eu-west-2` for London proximity if it meets
   model needs) and list the account-visible text and embedding models:

   ```powershell
   aws bedrock list-foundation-models --profile labledger-dev --region <aws-region> --by-output-modality TEXT --query "modelSummaries[].modelId" --output table
   aws bedrock list-foundation-models --profile labledger-dev --region <aws-region> --by-output-modality EMBEDDING --query "modelSummaries[].modelId" --output table
   ```

5. Select one reasoning model and one embedding model that both appear, then
   set `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_EMBEDDING_MODEL_ID`, and the
   matching `EMBEDDING_DIM` in the ignored `.env` file. Model IDs and the chosen
   region are safe to report; do not report credentials or the AWS account ID.

### 4. Install the P1 Python prerequisite

Python 3.11.5 is the only current interpreter. Before P1, install and verify
Python 3.12:

```powershell
winget install --id Python.Python.3.12 --exact
py -3.12 --version
```

## Blockers

- The CockroachDB cluster does not yet have verifiable local configuration and
  neither `ccloud` nor the CockroachDB SQL client is installed.
- AWS CLI and an AWS profile are absent, so `sts get-caller-identity` and
  account-specific Bedrock model/region checks cannot run.
- Devpost registration/draft creation requires the user's authenticated browser
  session and acceptance of the competition rules.
- Therefore P0's full gate is not satisfied and P1 must not start.

## Files changed

- `.env.example`
- `.gitignore`
- `AGENTS.md`
- `LICENSE`
- `README.md`
- `RUNBOOK.md`
- `STATUS.md`
- `TODO.md`
- `scripts/verify_p0.py`

## Commands run

- Read all required Markdown files in bounded chunks.
- Inspected Git state, remotes, runtimes, CLI availability, configuration-file
  presence, and environment-variable-name presence without printing values.
- Ran `gh auth status`, created the public GitHub repository, and verified its
  visibility/default branch/license via `gh repo view` and `gh api`.
- Ran `python -m py_compile scripts/verify_p0.py`.
- Ran `python scripts/verify_p0.py` before staging (expected tracking/remote
  failures) and after staging (7/7 pass).
- Ran `git diff --cached --check`, staged the P0 files, committed them, and
  pushed `main` to `origin`.

## Next

- Complete the four `NEEDS_USER_ACTION` sections above.
- Re-run `python scripts/verify_p0.py` and the read-only cloud identity/connection
  checks.
- Mark the four blocked P0 tasks complete only after their evidence is verified.
- Do not begin P1 until the P0 gate passes.
