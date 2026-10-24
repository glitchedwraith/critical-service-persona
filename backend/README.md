# Backend (P1)

TrueSignal backend — AWS SAM + Lambda (Python 3.12) + DynamoDB. See [PLAN.md](PLAN.md) for the phased implementation and [../plan.md](../plan.md) §3 for the API contract.

## Local dev

Prereqs: `sam`, `docker`, Python 3.12.

### 1. Start DynamoDB Local

```sh
docker network create truesignal-net
docker run -d --name dynamodb-local --network truesignal-net \
  -p 8000:8000 amazon/dynamodb-local
```

To stop: `docker stop dynamodb-local && docker rm dynamodb-local`.

### 2. Create local tables + seed system clock

```sh
python scripts/create_local_tables.py
```

Idempotent. Seeds the `system` singleton with `sim_clock=04:30` so `clock.now()` works immediately.

### 3. Build + run

```sh
sam build
sam local start-api --env-vars env.json --docker-network truesignal-net
```

API base URL: `http://localhost:3000`.

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
```

## Deploy to AWS

```sh
sam build
sam deploy --guided           # first time, creates samconfig entries
sam deploy                    # subsequent, uses [default] profile
sam deploy --config-env prod  # prod stack
```

API URL is in the stack outputs after deploy.

## Routes

Full contract: [../plan.md §3.2](../plan.md). Curl examples land here as each phase completes.

| Phase | Route | Status |
|---|---|---|
| 2 | `GET /state` | done |
| 2 | `POST /reset` | done |
| 3 | `POST /sms/inbound` | done |
| 4 | `POST /rumors/{id}/verify` | pending |
| 4 | `POST /outbound/{id}/edit` | pending |
| 4 | `POST /outbound/{id}/approve` | pending |
| 5 | `POST /chaos/{action}` | pending |
