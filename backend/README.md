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

Smoke test:
```sh
curl http://localhost:3000/state
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
| 0 | all routes return skeleton payload | done |
| 2 | `GET /state` | pending |
| 2 | `POST /reset` | pending |
| 3 | `POST /sms/inbound` | pending |
| 4 | `POST /rumors/{id}/verify` | pending |
| 4 | `POST /outbound/{id}/edit` | pending |
| 4 | `POST /outbound/{id}/approve` | pending |
| 5 | `POST /chaos/{action}` | pending |
