# Backend (P1)

TrueSignal backend — Python 3.12 Lambda handler + DynamoDB + real Amazon Bedrock (Haiku 4.5 via inference profile). See [PLAN.md](PLAN.md) for the phased implementation and [../plan.md](../plan.md) §3 for the API contract.

## Local dev (recommended for the demo)

Runs the full backend on `localhost:3000` using DynamoDB Local in Docker + real Bedrock Converse calls. **This is the loop we validated end-to-end** — all 6 chaos actions, verify/approve/delivery, and the resolved transition all work against real Haiku 4.5.

### Prereqs

- `docker` (Docker Desktop running)
- Python 3.12+ (we use a venv)
- `.env` at repo root with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` and `AWS_DEFAULT_REGION=us-east-1`. These need Bedrock Converse access on `us.anthropic.claude-haiku-4-5-20251001-v1:0` (override via `BEDROCK_MODEL_ID`).

### 1. Start DynamoDB Local (shared-DB mode)

```sh
docker network create truesignal-net 2>/dev/null || true
docker run -d --name dynamodb-local --network truesignal-net \
  -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

The `-sharedDb` flag is important: without it DynamoDB Local partitions by AWS access-key id, so the seed script and the server would see different databases.

To stop: `docker stop dynamodb-local && docker rm dynamodb-local`.

### 2. Create tables + seed

```sh
python3 -m venv /tmp/truesignal-venv
/tmp/truesignal-venv/bin/pip install boto3
/tmp/truesignal-venv/bin/python scripts/create_local_tables.py
```

### 3. Run the backend

```sh
set -a && source .env && set +a
/tmp/truesignal-venv/bin/python scripts/run_local.py
```

Listens on `http://localhost:3000`. Routes match the deployed SAM API exactly. DynamoDB calls go to the local container; Bedrock calls go to real AWS.

> `scripts/run_local.py` is a lightweight `http.server` shim around `app.lambda_handler` — avoids `sam local start-api`, which doesn't find Docker Desktop's non-standard socket on macOS without extra fiddling.

## Deploy to AWS

```sh
sam build
sam deploy --guided           # first time, creates samconfig entries
sam deploy                    # subsequent, uses [default] profile
sam deploy --config-env prod  # prod stack
```

The template is correct and ready. Needs an AWS account with normal IAM privileges (workshop/sandbox accounts that block `iam:CreateRole` / `iam:PassRole` won't work — see commit history for details). API URL appears in the stack outputs.

Smoke tests:
```sh
# Current state (sim clock, tables, trace)
curl -s http://localhost:3000/state | jq .

# Re-seed system singleton (and P4's data when available)
curl -s -X POST http://localhost:3000/reset | jq .

# Inbound SMS - creates/joins a rumor cluster, drafts an individual reply
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

# Edit the current draft (re-runs validator stub)
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

## Routes

Full contract: [../plan.md §3.2](../plan.md). Curl examples land here as each phase completes.

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
