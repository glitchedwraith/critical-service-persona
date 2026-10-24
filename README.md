# TrueSignal — Emergency Information Continuity Engine

SpartHill Hacks 2026 | AWS Track

When the city's website goes dark after a disaster, TrueSignal keeps residents getting trustworthy, timestamped answers. It detects rumors from incoming SMS traffic, drafts clarifications grounded in official data, routes them through human approval, and tracks whether each rumor dies down or comes back.

## How it works

1. **Inbound SMS** arrives (simulated). Bedrock Step 1 extracts claims, matches or creates a rumor cluster.
2. When a cluster hits **5+ messages in 10 sim-minutes**, it becomes an **Emerging Rumor** and Bedrock Step 2 verifies it against official shelter/bulletin data.
3. A **code validator** enforces safety rules (IDs exist, addresses match, source authority, expiry checks, "as of HH:MM" timestamps, 300-char cap) before anything is shown or sent.
4. **Dana** (the EOC officer) reviews and approves broadcast clarifications. Individual replies auto-send only when the validator passes with non-expired authority-1/2 evidence.
5. After send, the system **monitors** the rumor rate — resolves it on a 50%+ drop, or reopens it if the rate holds.

## Architecture

```
React (Vite) single page ── polls every 2s ──> API Gateway (HTTP API)
   (Amplify Hosting / S3)                           |
                                                     v
                                     Lambda (Python 3.12, one function, routes)
                                      |- /sms/inbound   -> Step 1 -> cluster
                                      |- /rumors/{id}/verify -> Step 2 -> validator
                                      |- /outbound/{id}/approve -> send (simulated)
                                      |- /chaos/{action}
                                      '- /state  (everything the screen needs)
                                                     |
                                +--------------------+-------------------+
                                v                    v                   v
                         Amazon Bedrock          DynamoDB           S3 (optional)
                    (Converse + tool use)    (7 tables)
```

- **Bedrock model:** Claude Haiku 4.5 via US inference profile (`us.anthropic.claude-haiku-4-5-20251001-v1:0`), overridable via `BEDROCK_MODEL_ID`
- **Simulated clock:** all time logic uses `system.sim_clock`, not wall time — lets you expire bulletins and advance time live in the demo
- **Polling, not WebSockets:** 2-second interval keeps the dashboard live with much less to go wrong

## Repo layout

```
README.md                  # this file
plan.md                    # team responsibilities + integration contract
TrueSignal-Plan-v3.md     # full spec (persona, pipeline, validator rules, demo script)
template.yaml              # SAM: HTTP API, 1 Lambda, 7 DynamoDB tables
samconfig.toml             # SAM deploy config (default + prod)
env.json                   # SAM local env-var overrides
.env                       # AWS creds (gitignored, never commit)

backend/
  app.py                   # Lambda handler + path router
  db.py                    # DynamoDB helpers (get/put/scan/update)
  clock.py                 # sim-clock utilities (now, advance, is_expired)
  chaos.py                 # 6 chaos endpoints
  rumor_loop.py            # monitoring -> resolved/reopened loop
  pipeline.py              # real Bedrock pipeline (Step 1 extract, Step 2 verify)
  pipeline_stub.py         # canned outputs for offline dev
  validator.py             # safety rules (IDs, addresses, authority, expiry)
  validator_stub.py        # pass-through stub
  templates.py             # fallback reply templates
  requirements.txt         # boto3
  README.md                # detailed backend docs
  PLAN.md                  # phased implementation plan

scripts/
  start_backend.sh         # one-command local dev setup (venv + DynamoDB + seed + server)
  create_local_tables.py   # creates 7 DynamoDB Local tables + seeds system singleton
  run_local.py             # lightweight http.server shim around lambda_handler
```

## Quick start (local dev)

### Prerequisites

- Docker Desktop running
- Python 3.12+
- `.env` at repo root with AWS credentials that have Bedrock access:
  ```
  AWS_DEFAULT_REGION=us-east-1
  AWS_ACCESS_KEY_ID=<your-key>
  AWS_SECRET_ACCESS_KEY=<your-secret>
  AWS_SESSION_TOKEN=<your-token>          # if using temporary creds
  ```

### One-command start

```sh
./scripts/start_backend.sh
```

This handles everything: creates a Python venv, starts DynamoDB Local in Docker, creates tables, seeds data, and starts the backend on `http://localhost:3000`.

### Manual steps (if you prefer)

See [backend/README.md](backend/README.md) for the full 6-step walkthrough.

## API routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/state` | Full dashboard state (shelters, rumors, outbound, trace, sim clock) |
| `POST` | `/sms/inbound` | Receive a simulated SMS `{from, role, zone, text}` |
| `POST` | `/rumors/{id}/verify` | Verify a rumor against official data via Bedrock |
| `POST` | `/outbound/{id}/edit` | Edit a draft clarification (re-runs validator) |
| `POST` | `/outbound/{id}/approve` | Approve + send `{approver}` |
| `POST` | `/chaos/{action}` | Trigger a chaos event (see below) |
| `POST` | `/reset` | Re-seed all tables for a clean demo |

### Chaos actions

| Action | Effect |
|---|---|
| `city_site_down` | Flips `city_site_online=false`; answers cite cached bulletins with age |
| `rumor_wave` | Injects 12 "Shelter A closed" variants; cluster count climbs, Emerging Rumor card appears |
| `shelter_a_full` | Shelter manager (authority 2) reports SH-A full; answers redirect to SH-D |
| `conflicting_report` | Resident (authority 4) claims "Shelter D closed"; stays unverified, never overrides official data |
| `advance_clock` | `{minutes: 45}` — advances sim clock, triggers rumor-loop tick |
| `expire_bulletin` | `{id: "B-001"}` — sets bulletin expiry before sim clock; system says "can't confirm" |

## Smoke test

```sh
# Dashboard state
curl -s http://localhost:3000/state | jq .

# Send a text
curl -s -X POST http://localhost:3000/sms/inbound \
  -H 'Content-Type: application/json' \
  -d '{"from":"+1-555-0101","role":"resident","zone":"B","text":"heard shelter A closed??"}' | jq .

# Trigger a rumor wave, then check emerging status
curl -s -X POST http://localhost:3000/chaos/rumor_wave | jq .
curl -s http://localhost:3000/state | jq '.rumors[0] | {id, emerging, message_count, status}'

# Verify -> edit -> approve flow
curl -s -X POST http://localhost:3000/rumors/R-001/verify | jq .
DRAFT=$(curl -s http://localhost:3000/state | jq -r '.rumors[0].clarification_id')
curl -s -X POST http://localhost:3000/outbound/$DRAFT/approve \
  -H 'Content-Type: application/json' \
  -d '{"approver":"Dana"}' | jq .
```

## Deploy to AWS

```sh
sam build
sam deploy --guided           # first time
sam deploy                    # subsequent deploys
sam deploy --config-env prod  # prod stack
```

Requires an AWS account with normal IAM privileges (`iam:CreateRole`, `iam:PassRole`, `iam:TagRole`). Workshop/sandbox accounts that block these won't work — use the local flow above for demos. API URL appears in the stack outputs.

## DynamoDB tables

Seven tables, all with a simple `id` (String) hash key, PAY_PER_REQUEST billing:

| Table | Contents |
|---|---|
| `sources` | Who said it + authority level (1=EOC, 2=shelter mgr, 3=news, 4=resident) |
| `bulletins` | Official info cached before the outage, with publish/verify/expiry times |
| `shelters` | Live shelter facts (status, capacity, occupancy, source, timestamps) |
| `messages` | Inbound SMS with extracted claims and cluster assignment |
| `rumors` | Claim clusters with verdict, evidence, rate history, resolution status |
| `outbound` | Everything TrueSignal sends (drafts, approved, sent, delivered) |
| `system` | Sim clock, city site status, approver name, trace log |

## Environment variables

| Variable | Default (local) | Purpose |
|---|---|---|
| `AWS_ACCESS_KEY_ID` / `SECRET` / `SESSION_TOKEN` | — | AWS creds for Bedrock |
| `AWS_DEFAULT_REGION` | — | `us-east-1` (Haiku 4.5 inference profile is region-specific) |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Override for different model |
| `DYNAMODB_ENDPOINT` | `http://localhost:8000` | DynamoDB Local; unset in prod |
| `TABLE_SOURCES` ... `TABLE_SYSTEM` | `truesignal-local-<name>` | 7 table name vars |
| `PORT` | `3000` | Local server bind port |

## Team

| Role | Owns |
|---|---|
| **P1** Backend | SAM infra, Lambda router, DynamoDB, sim clock, chaos, rumor-loop, delivery sim |
| **P2** AI + Safety | Bedrock pipeline (extract + verify), prompts, validator, templates |
| **P3** Frontend | React dashboard, phone simulator, polling, chaos bar, pipeline trace |
| **P4** Data + QA | Seed data, rumor scripts, test cases, demo script, video |

See [plan.md](plan.md) for the full integration contract and [TrueSignal-Plan-v3.md](TrueSignal-Plan-v3.md) for the complete spec.
