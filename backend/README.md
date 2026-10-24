# Backend (P1)

TrueSignal backend — Python 3.12 Lambda handler + DynamoDB + real Amazon Bedrock (Haiku 4.5 via a US inference profile). See [PLAN.md](PLAN.md) for the phased implementation and [../plan.md](../plan.md) §3 for the API contract.

---

## Environment variables

| Var | Where set | Required for | Default (local) | Notes |
|---|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | `.env` at repo root | Bedrock | — | temporary workshop creds work; see redaction note below |
| `AWS_SECRET_ACCESS_KEY` | `.env` | Bedrock | — | |
| `AWS_SESSION_TOKEN` | `.env` | Bedrock | — | only present for temporary creds (STS/SSO) |
| `AWS_DEFAULT_REGION` | `.env` | Bedrock + DynamoDB | — | set to `us-east-1`; Haiku 4.5 inference profile is region-specific |
| `AWS_BEARER_TOKEN_BEDROCK` | `.env` (optional) | — | — | present in some workshop `.env` files; not used by our code (we use boto3 sig-v4) |
| `BEDROCK_MODEL_ID` | shell / env.local.json | Bedrock | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | override to use Sonnet / Opus / Nova |
| `DYNAMODB_ENDPOINT` | `scripts/run_local.py` defaults | DynamoDB Local | `http://localhost:8000` | unset in production so boto3 talks to real AWS |
| `TABLE_SOURCES` ... `TABLE_SYSTEM` | run_local.py / env.json / SAM | DynamoDB | `truesignal-local-<name>` | 7 vars, one per table |
| `PORT` | shell (optional) | local server bind | `3000` | override if 3000 is in use |

**`.env` layout** at repo root (gitignored):

```sh
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_SESSION_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # if using temporary creds
AWS_BEARER_TOKEN_BEDROCK=xxxxxxxxxxxxxxxxxxxxxxxxx            # optional
```

> `.env` and `env.local.json` are in `.gitignore` — never commit them. If sharing via chat, redact values (`***`) and keep key names only.

---

## Local dev (full backend on `localhost:3000`, real Bedrock)

This is the loop we validated end-to-end — all 6 chaos actions, verify/approve/delivery, and the resolved transition all work against real Haiku 4.5.

### Prereqs

- Docker Desktop running (just the daemon; we don't use `sam local`)
- Python 3.12+ on `PATH` as `python3`
- `.env` at repo root (see table above)
- Bedrock Converse access on `us.anthropic.claude-haiku-4-5-20251001-v1:0` in the AWS account that owns the keys (every TrueSignal AWS/workshop account should have this by default)

### 1. Create a Python venv + install `boto3`

```sh
python3 -m venv /tmp/truesignal-venv
/tmp/truesignal-venv/bin/pip install boto3
```

(Any venv path works — this is just so `boto3` lives somewhere pip can write to. The repo's Lambda bundle ships its own `boto3`; this venv is only for the local scripts.)

### 2. Start DynamoDB Local (shared-DB mode)

```sh
docker network create truesignal-net 2>/dev/null || true
docker run -d --name dynamodb-local --network truesignal-net \
  -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

**The `-sharedDb` flag matters.** Without it DynamoDB Local partitions by AWS access-key id, so `scripts/create_local_tables.py` (seeded with the fake `"local"` key) and `run_local.py` (seeded with your real workshop key) would see different databases.

To stop later: `docker stop dynamodb-local && docker rm dynamodb-local`.

### 3. Create the 7 tables + seed the system singleton

```sh
/tmp/truesignal-venv/bin/python scripts/create_local_tables.py
```

Idempotent. Seeds `system/singleton` with `sim_clock=04:30`, so `clock.now()` works immediately. Does **not** seed shelters / bulletins / sources — that's P4's data (step 4 below is a stop-gap).

### 4. (Interim, until P4's seed lands) Seed shelters + bulletins + sources

Bedrock needs grounded data to answer against. Paste this into a shell:

```sh
/tmp/truesignal-venv/bin/python - <<'PY'
import boto3, os
os.environ.setdefault('AWS_ACCESS_KEY_ID','x'); os.environ.setdefault('AWS_SECRET_ACCESS_KEY','x')
r = boto3.resource('dynamodb', endpoint_url='http://localhost:8000', region_name='us-east-1')
seeds = {
    'truesignal-local-sources': [
        {'id':'SRC-EOC','name':'City EOC','authority':1},
        {'id':'SRC-MGR-A','name':'Shelter A manager','authority':2},
        {'id':'SRC-MGR-D','name':'Shelter D manager','authority':2},
    ],
    'truesignal-local-shelters': [
        {'id':'SH-A','name':'Shelter A — Lincoln HS Gym','address':'123 Example Ave',
         'status':'open','capacity':300,'occupancy':240,
         'status_source_id':'SRC-EOC','status_updated_at':'04:10','status_expires_at':'05:10'},
        {'id':'SH-D','name':'Shelter D — Jefferson Rec Center','address':'456 Pine St',
         'status':'open','capacity':250,'occupancy':60,
         'status_source_id':'SRC-EOC','status_updated_at':'04:10','status_expires_at':'06:00'},
    ],
    'truesignal-local-bulletins': [
        {'id':'B-001','source_id':'SRC-EOC','title':'Shelters open',
         'body':'Shelters A (SH-A, 123 Example Ave) and D (SH-D, 456 Pine St) are open.',
         'published_at':'04:00','last_verified_at':'04:10','expires_at':'06:00','status':'active'},
    ],
}
for tbl, items in seeds.items():
    t = r.Table(tbl)
    for it in items: t.put_item(Item=it)
    print(f'seeded {tbl}: {len(items)}')
PY
```

### 5. (Optional) Verify Bedrock creds before starting the server

```sh
set -a && source .env && set +a
aws bedrock-runtime converse --region us-east-1 \
  --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --messages '[{"role":"user","content":[{"text":"Reply with just the word pong"}]}]' \
  --inference-config '{"maxTokens":10}' \
  --query 'output.message.content[0].text' --output text
```

Expect `pong`. If you see `ResourceNotFoundException` the model is retired or not enabled in your account; `AccessDeniedException` means the creds don't have Bedrock permissions.

### 6. Run the backend

```sh
set -a && source .env && set +a
/tmp/truesignal-venv/bin/python scripts/run_local.py
```

Listens on `http://localhost:3000`. Routes match the deployed SAM API exactly. DynamoDB calls go to the local container; Bedrock calls go to real AWS. Logs each request to stderr.

> `scripts/run_local.py` is a lightweight `http.server` shim around `app.lambda_handler`. We don't use `sam local start-api` because it can't find Docker Desktop's socket on macOS (`~/.docker/run/docker.sock`) without extra plumbing. The shim is ~90 lines and simulates the API Gateway v2 event shape.

---

## Smoke tests (against the running local server)

```sh
# Current state (sim clock, tables, trace)
curl -s http://localhost:3000/state | jq .

# Re-seed system singleton (and P4's data when available)
curl -s -X POST http://localhost:3000/reset | jq .

# Inbound SMS - creates/joins a rumor cluster, drafts an individual reply (real Bedrock)
curl -s -X POST http://localhost:3000/sms/inbound \
  -H 'Content-Type: application/json' \
  -d '{"from":"+1-555-0101","role":"resident","zone":"B","text":"heard shelter A closed??"}' | jq .

# Fire the emerging rule: post 5 similar messages
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:3000/sms/inbound \
    -H 'Content-Type: application/json' \
    -d "{\"from\":\"+1-555-010$i\",\"role\":\"resident\",\"zone\":\"B\",\"text\":\"is shelter A shut $i\"}" >/dev/null
done
curl -s http://localhost:3000/state | jq '.rumors[0] | {id, emerging, message_count, rate_per_10min, status, clarification_id}'

# Manual verify (idempotent — mints a fresh draft, points rumor.clarification_id at it)
curl -s -X POST http://localhost:3000/rumors/R-001/verify | jq .

# Edit the current draft (re-runs validator)
DRAFT=$(curl -s http://localhost:3000/state | jq -r '.rumors[0].clarification_id')
curl -s -X POST http://localhost:3000/outbound/$DRAFT/edit \
  -H 'Content-Type: application/json' \
  -d '{"text":"UPDATE 04:10: Shelter A is OPEN (Lincoln HS Gym). Source: City EOC."}' | jq .

# Approve: draft -> sent, rumor -> monitoring, baseline rate captured
curl -s -X POST http://localhost:3000/outbound/$DRAFT/approve \
  -H 'Content-Type: application/json' \
  -d '{"approver":"Dana"}' | jq .

# Delivery sim: sent -> delivered after ~2 wall-seconds, promoted lazily on next /state
sleep 3 && curl -s http://localhost:3000/state | jq '.outbound[] | {id, state, delivered_at}'

# Chaos: six actions, each mutates state
curl -s -X POST http://localhost:3000/chaos/city_site_down | jq .
curl -s -X POST http://localhost:3000/chaos/rumor_wave | jq .
curl -s -X POST http://localhost:3000/chaos/shelter_a_full | jq .
curl -s -X POST http://localhost:3000/chaos/conflicting_report | jq .
curl -s -X POST http://localhost:3000/chaos/advance_clock -H 'Content-Type: application/json' -d '{"minutes":45}' | jq .
curl -s -X POST http://localhost:3000/chaos/expire_bulletin -H 'Content-Type: application/json' -d '{"id":"B-001"}' | jq .
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `GET /state` → 500 `ResourceNotFoundException: non-existent table` | Table-partitioning issue. Restart DynamoDB Local with `-sharedDb` (step 2) and re-run step 3. |
| `pipeline.verify` crashes with `Object of type Decimal is not JSON serializable` | Already patched (`_jdumps`); update your branch. |
| Bedrock calls fail with `UnrecognizedClientException` | Session token expired — refresh `.env` from your workshop console and `source .env` again. |
| Bedrock calls fail with `ResourceNotFoundException: model version has reached end of life` | Model ID retired. Set `BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0` or pick another current ID from `aws bedrock list-inference-profiles --region us-east-1`. |
| `clock.now()` raises `system singleton missing` | Run step 3 (`create_local_tables.py`) or `POST /reset`. |
| Port 3000 already in use | `PORT=3001 /tmp/truesignal-venv/bin/python scripts/run_local.py` and point the frontend at the new URL. |

---

## Deploy to AWS

```sh
sam build
sam deploy --guided           # first time, creates samconfig entries
sam deploy                    # subsequent, uses [default] profile
sam deploy --config-env prod  # prod stack
```

The template is correct and ready. Needs an AWS account with normal IAM privileges (workshop/sandbox accounts that block `iam:CreateRole` / `iam:PassRole` / `iam:TagRole` won't work — the local flow above is the demo path). API URL appears in the stack outputs.

---

## Routes

Full contract: [../plan.md §3.2](../plan.md).

| Phase | Route | Status |
|---|---|---|
| 2 | `GET /state` | done |
| 2 | `POST /reset` | done |
| 3 | `POST /sms/inbound` | done |
| 4 | `POST /rumors/{id}/verify` | done |
| 4 | `POST /outbound/{id}/edit` | done |
| 4 | `POST /outbound/{id}/approve` | done |
| 4 | delivery sim (sent → delivered after ~2s wall) | done |
| 5 | `POST /chaos/{action}` (6 actions) | done |
| 5 | rumor_loop (monitoring → resolved/reopened + evidence_expired) | done |
| 6 | real Bedrock pipeline (`backend/pipeline.py`) wired in | done |
| 6 | AWS Lambda deploy | ready, pending non-workshop AWS creds |
