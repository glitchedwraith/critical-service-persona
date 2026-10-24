# Backend Implementation Plan (P1)

Owner: P1 (backend). Scope derived from [../plan.md](../plan.md) §1, §3, §5. Contract source of truth: [../plan.md](../plan.md) §3; prose details: [../TrueSignal-Plan-v3.md](../TrueSignal-Plan-v3.md).

**Goal:** ship the backend half of one end-to-end loop — inbound text → cluster → emerging rumor → verify → draft → approve → send → monitored → resolved/reopened — with chaos buttons wired, running first locally and then on AWS.

**Dev target:** local-first via `sam local start-api` + DynamoDB Local (docker), then `sam deploy` to AWS when the loop is green.

---

## Phase 0 — Skeleton (unblocks P2, P3, P4)

Files to create:
- `backend/app.py` — Lambda handler, path routing
- `backend/db.py` — DynamoDB helpers
- `backend/clock.py` — sim-clock utilities
- `backend/chaos.py` — chaos endpoints
- `backend/rumor_loop.py` — monitoring/resolution loop
- `backend/pipeline_stub.py` — canned outputs matching plan.md §3.4
- `backend/requirements.txt` — `boto3`, `strands-agents` (P2 adds Bedrock deps)
- `template.yaml` — SAM: HTTP API, 1 Lambda, 7 DynamoDB tables, CORS on, Bedrock IAM

Also:
- `samconfig.toml` with a `local` and `prod` config
- `backend/README.md` scaffold with "how to run locally" and "how to deploy"
- `.gitignore` for `.aws-sam/`, `__pycache__/`, `*.pyc`

**Done when:** `sam build` succeeds and `sam local start-api` boots.

## Phase 1 — Primitives

- `db.py`: `get(table, key)`, `put(table, item)`, `scan(table)`, `update(table, key, expr, vals)`. Table names come from env vars set by SAM (`TABLE_SOURCES`, `TABLE_BULLETINS`, etc.). Single `boto3.resource("dynamodb")` client; endpoint URL honours `DYNAMODB_ENDPOINT` so local runs hit DynamoDB Local.
- `clock.py`:
  - `now() -> "HH:MM"` reads `system` table singleton
  - `minutes_between(a, b) -> int`
  - `is_expired(ts) -> bool` compares to `now()`
  - `advance(minutes: int)` — writes new `sim_clock` to `system`
  - `parse("HH:MM") -> minutes_since_midnight` internal helper (handles the hackathon day; no date math needed)
- `pipeline_stub.py`: `extract()` + `verify()` returning plan.md §3.4 shapes. Hard-code two fixtures:
  - "shelter A closed" → cluster `R-002`, verdict `contradicted`, `auto_send_ok=True`
  - unknown entity → `cluster_match=null`, new cluster, `auto_send_ok=False`

**Done when:** both stub functions importable; `clock.now()` reads a seeded `system` row from DynamoDB Local.

## Phase 2 — Router + `GET /state` (unblocks P3)

- `app.py`: Lambda handler reads `event["routeKey"]`, dispatches to handlers. One `lambda_handler` entry point for everything.
- `GET /state`: assemble plan.md §3.3 shape:
  - Scan each table, join where needed
  - Compute `expired` (bulletins/shelters), `age_min` (bulletins), `emerging` (rumors with ≥5 msgs in last 10 sim-min), `outdated` (outbound flagged by chaos), `evidence_expired` (rumors with any expired evidence)
  - Return `trace` from an append-only list stored on the `system` row (cap at 50 entries, newest first)
- `POST /reset`: import `seed.seed` lazily and call it; swallows ImportError if P4 hasn't shipped yet.
- CORS: `Access-Control-Allow-Origin: *` on all responses so P3 can hit it from Vite dev server.

**Done when:** P3 can poll `/state` and get the mock-matching shape; a curl example in `backend/README.md`.

## Phase 3 — Inbound + clustering

- `POST /sms/inbound {from, role, zone, text}`:
  1. Write to `messages` with `received_at = clock.now()`
  2. Call `pipeline.extract(text, active_clusters, known_entity_ids)` (stub for now)
  3. If `cluster_match`: update rumor's `message_count`, append to `rate_per_10min` (bucket by current 10-sim-min window)
  4. Else if `new_cluster_claim`: create a new `rumors` row with `status=new`
  5. Append trace: `{at: now, message_id, step:"step1", ok, detail, ms}`
  6. Emerging check: if `message_count` in last 10 sim-min ≥ 5 → set `emerging=true`, call verify handler inline
  7. Individual reply: if the inbound was a direct question → produce holding reply (template) unless `auto_send_ok`; return `reply` in response body
- Rate buckets live on the rumor row as `rate_per_10min: [int, int, int]` — index by `(now_minutes - first_seen_minutes) // 10`.

**Done when:** typing a text through the stub pipeline produces a rumor row and a reply; emerging rule fires at the 5th message within a 10-min window.

## Phase 4 — Verify + approve + delivery sim

- `POST /rumors/{id}/verify`: load rumor + referenced shelters/bulletins/sources rows, call `pipeline.verify(...)`, persist `verdict`, `current_status_known`, `evidence`, and create `outbound` row with `state=draft`. Store validator metadata (`passed`, `flags`, `fallback_used`, `auto_send_ok`) on the rumor for the UI.
- `POST /outbound/{id}/edit {text}`: update text, re-run `validator.validate()` on the edited draft (stub returns `(draft, [])` until P2 lands).
- `POST /outbound/{id}/approve {approver}`: `draft` → `approved` → immediately mark `sent` with `approved_by`, `approved_at`. Schedule simulated delivery (see below).
- Simulated delivery: after approve, flip `sent → delivered` on the next request handling tick (lazy: check in `GET /state` for any outbound in `sent` older than ~2s and promote to `delivered`). Failure path off by default; add a system flag `delivery_fail_mode` toggled by chaos later if needed.
- Individual reply auto-send on `/sms/inbound`: writes outbound directly with `state=sent`, skipping Dana.

**Done when:** full happy path from inbound → verify → approve → delivered works end-to-end against the stub.

## Phase 5 — Chaos + resolution loop

Six chaos actions in `chaos.py`:
| Action | Behavior |
|---|---|
| `city_site_down` | set `system.city_site_online=false` |
| `rumor_wave` | read `seed/scripts/rumors.json`, inject 12 "Shelter A closed" messages across a few zones |
| `shelter_a_full` | upsert an authority-2 shelter-manager report; set `SH-A.status=full`; mark any already-sent clarification about SH-A as `outdated=true` |
| `conflicting_report` | inject an authority-4 resident message claiming "Shelter D closed" |
| `advance_clock {minutes}` | `clock.advance(minutes)`; triggers rumor_loop tick |
| `expire_bulletin {id}` | set `expires_at < sim_clock` on the bulletin |

`rumor_loop.py`:
- Runs on every `/sms/inbound` and every clock-advancing chaos call
- For each rumor with `status=monitoring`, compare the two 10-sim-min windows after send against the pre-send baseline rate
- ≥ 50% drop → `status=resolved`
- Flat or rising → `status=reopened`; call `pipeline.verify()` to draft a follow-up outbound
- If any rumor evidence row expires during monitoring → set `evidence_expired=true` on the rumor
- Pre-send baseline rate stored on rumor row at approve time (`baseline_rate_per_10min`)

**Done when:** all six chaos buttons produce the "what judges see" behavior in plan v3 §9, and the monitor transitions correctly on `advance_clock`.

## Phase 6 — AWS deploy + integration

- `sam deploy --guided` to a sandbox stack, capture API base URL, post in team chat
- Verify IAM role allows `bedrock:InvokeModel` / `Converse` on P2's chosen model (plan.md §3.5)
- Swap `pipeline_stub` → `pipeline` import in `app.py` once P2 signals ready (one-line change)
- Final curl examples in `backend/README.md` — one per endpoint, DoD per plan.md §2

---

## Local dev → AWS path

**Local (phases 0–5):**
- DynamoDB Local in Docker: `docker run -p 8000:8000 amazon/dynamodb-local`
- Env: `DYNAMODB_ENDPOINT=http://host.docker.internal:8000`, `AWS_REGION=us-east-1`, dummy creds
- Create tables with a `scripts/create_local_tables.py` that mirrors `template.yaml`
- Run API: `sam local start-api --env-vars env.json`
- Seed: `python -m seed.seed` (P4's script, invoked from `/reset` too)
- Bedrock calls during local dev: hit real AWS Bedrock with the user's creds (DynamoDB Local only; Bedrock has no good local emulator)

**AWS (phase 6):**
- `sam deploy --config-env prod` → creates real tables + Lambda + HTTP API
- Base URL goes into frontend `.env` and team chat

---

## Interfaces P1 depends on

- `pipeline.extract()`, `pipeline.verify()` from P2 — stubbed in `pipeline_stub.py` until ready (plan.md §3.4)
- `validator.validate()` from P2 — stubbed as pass-through until ready
- `seed.seed()` from P4 — invoked by `/reset`; falls back to hand-written rows if missing
- `seed/scripts/rumors.json` from P4 — read by `rumor_wave` chaos; fall back to inline fixture

## Open items

- Confirm Bedrock model ID with P2 before writing the IAM policy in `template.yaml` (plan.md §3.5)
- Decide whether delivery-sim timing should be purely lazy (promote on next `/state`) or use EventBridge — lazy is simpler, EventBridge is more realistic. Default: lazy.
