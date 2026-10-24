# TrueSignal — Team Responsibilities (4 people)

Derived from [TrueSignal-Plan-v3.md](TrueSignal-Plan-v3.md). That doc is the spec; this one says **who owns what, which files they own, and the contracts that let everyone work without waiting on each other.**

> **North star:** one end-to-end loop that runs: inbound text → cluster → emerging rumor → verify → validate → Dana approves → sent → monitored → resolved/reopened.

**Never cut:** validator, timestamps, approve flow, rumor-resolution tracking.

---

## 1. Who owns what

| | Person | Owns | Main files |
|---|---|---|---|
| **P1** | Backend | AWS infra (SAM), DynamoDB tables, Lambda router, `/state`, sim clock, chaos endpoints, send/delivery sim, rumor-resolution monitor | `template.yaml`, `backend/app.py`, `backend/db.py`, `backend/clock.py`, `backend/chaos.py`, `backend/rumor_loop.py` |
| **P2** | AI + safety | Bedrock pipeline (Step 1, Step 2, Step 3 stretch), prompts, tool schemas, **validator**, regenerate-once + template fallback, auto-send policy | `backend/pipeline.py`, `backend/prompts/`, `backend/validator.py`, `backend/templates.py` |
| **P3** | Frontend | The one screen, resident phone sim, polling, chaos bar, pipeline trace strip, hosting | `frontend/` (React + Vite) |
| **P4** | Data, QA, story | Seed data, rumor scripts, mock `/state`, validator + pipeline test cases, prompt-injection test, demo script, video, Box upload | `seed/`, `tests/`, `frontend/src/mock/state.json`, `demo/` |

**Change from v3 §11:** the validator moves from P1 to P2. It is tightly coupled to Step 2 output and the regenerate/fallback logic, and P1 already carries infra, routes, clock, chaos and the resolution loop. P4 writes the validator's test cases, and P2 codes against them.

---

## 2. How we work async

- **Contract first.** §3 below is the only thing everyone must agree on before splitting up. Once agreed, nobody changes it without posting in team chat and getting a 👍 from the people it affects.
- **Own your files.** Only edit files you own (§1, §4). Need something in someone else's file? Ask them, or leave a `# TODO(P#): ...` and ping them.
- **Never block on another person. Mock or stub instead:**
  - P3 builds against `frontend/src/mock/state.json` (P4) until the API is live; an env var switches mock ↔ live.
  - P1 ships `backend/pipeline_stub.py` returning canned Step 1 / Step 2 JSON, so routes work before P2's real pipeline lands. Swap the import when P2 says it's ready.
  - P2 develops and tests offline against P4's fixtures in `tests/fixtures/`; no DynamoDB or API needed.
  - P4 can write seed data, fixtures, tests and the demo script straight from v3 + this contract.
- **Branches + small PRs.** One branch per person or feature (`p1/state-endpoint`, `p2/validator`, ...). Merge to `main` often; keep `main` deployable.
- **Status in one place.** Each person ticks their checklist in §5 as they go (edit this file in your PR). Blockers go in team chat with `@owner`.
- **Definition of done** for any item: merged to `main`, works against the contract, and (for backend/AI) covered by at least one test or a curl example in the PR description.

---

## 3. Integration contract

### 3.1 Tables
Exactly the schemas in v3 §3: `sources`, `bulletins`, `shelters`, `messages`, `rumors`, `outbound`, `system`. Times are `"HH:MM"` strings in **sim time**. P1 creates the tables; P4 provides the seed data.

### 3.2 HTTP API (P1 implements, P3 calls)

| Method + path | Body | Returns |
|---|---|---|
| `GET /state` | — | the shape in §3.3 |
| `POST /sms/inbound` | `{from, role, zone, text}` | `{message_id, cluster_id, reply: outbound \| null}` |
| `POST /rumors/{id}/verify` | — | updated rumor + draft outbound |
| `POST /outbound/{id}/edit` | `{text}` | updated outbound (re-validated) |
| `POST /outbound/{id}/approve` | `{approver}` | outbound with `state` = `approved` → `sent` |
| `POST /chaos/{action}` | action-specific (below) | `{ok: true}` |
| `POST /reset` | — | reseeds all tables (for demo retakes) |

Chaos actions: `city_site_down`, `rumor_wave`, `shelter_a_full`, `conflicting_report`, `advance_clock` (`{minutes: 45}`), `expire_bulletin` (`{id}`).

### 3.3 `/state` response shape
```json
{
  "system":   { "sim_clock": "04:35", "city_site_online": false, "approver": "Dana",
                "cache_as_of": "04:10" },
  "messages": [ /* newest first, max 50, messages rows */ ],
  "rumors":   [ /* rumors rows + "emerging": bool, "outdated": bool, "evidence_expired": bool */ ],
  "outbound": [ /* outbound rows, newest first */ ],
  "shelters": [ /* shelters rows + "expired": bool */ ],
  "bulletins":[ /* bulletins rows + "expired": bool, "age_min": int */ ],
  "trace":    [ { "at": "04:33", "message_id": "M-017", "step": "step1|step2|validator|send",
                  "ok": true, "detail": "matched R-002", "ms": 812 } ]
}
```
Computed flags (`expired`, `age_min`, `emerging`) are calculated server-side from `sim_clock`, so the UI never does time logic.

### 3.4 Python interfaces between P1 and P2
```python
# backend/pipeline.py  (P2)
def extract(text: str, clusters: list[dict], entity_ids: list[str]) -> dict
    # -> v3 §4 Step 1 output, entity IDs already filtered to known ones
def verify(rumor: dict, shelters: list[dict], bulletins: list[dict],
           sources: list[dict], sim_clock: str) -> dict
    # -> v3 §4 Step 2 output, ALREADY passed through validator.validate()
    #    plus {"validator": {"passed": bool, "flags": [...], "fallback_used": bool},
    #          "auto_send_ok": bool}

# backend/validator.py  (P2)
def validate(draft: dict, ctx: dict) -> tuple[dict, list[str]]
    # ctx = {shelters, bulletins, sources, sim_clock}; returns (fixed_draft, flags)
```
P1 calls these from the routes. P2 never touches DynamoDB directly; P1 passes rows in. That keeps P2 testable offline against P4's fixtures.

### 3.5 Open decision (P2 owns)
The repo already imports **Strands `Agent` + `BedrockModel`** ([main.py](main.py)). P2 picks either Strands with structured output, or plain `boto3` `bedrock-runtime.converse` with `toolChoice` forcing a single tool, and records the choice here. Prefer plain `converse` if Strands gives trouble inside Lambda. The function signatures in §3.4 don't change either way.

---

## 4. Repo layout
```
template.yaml            # SAM: HTTP API, 1 Lambda, 7 DynamoDB tables      (P1)
backend/
  app.py                 # router                                         (P1)
  db.py  clock.py  chaos.py  rumor_loop.py  pipeline_stub.py              (P1)
  pipeline.py  validator.py  templates.py  prompts/                       (P2)
  requirements.txt                                                        (P1, P2 add deps via PR)
frontend/                # Vite + React                                   (P3)
  src/mock/state.json    # mock /state                                    (P4)
seed/
  seed.py  data/*.json  scripts/rumors.json                               (P4)
tests/
  test_validator.py  test_pipeline.py  fixtures/                          (P4 writes, P2 makes pass)
demo/
  script.md  qa-prep.md                                                   (P4)
```

---

## 5. Responsibilities

### P1 — Backend
**Infra**
- [ ] Repo skeleton (§4) and SAM `template.yaml`: 7 tables, 1 Lambda, HTTP API, CORS on
- [ ] Deploy works; API base URL posted in team chat and in the README
- [ ] Lambda IAM role allows Bedrock Converse on P2's chosen model

**Core**
- [ ] `db.py` helpers (get/put/scan per table)
- [ ] `clock.py`: `now()`, `minutes_between()`, `is_expired(ts)`, all based on `sim_clock`
- [ ] `pipeline_stub.py` with canned outputs matching §3.4
- [ ] `GET /state` returning the §3.3 shape with computed flags
- [ ] `POST /sms/inbound`: store message → `extract` → create/update rumor cluster, `message_count`, `rate_per_10min` → append trace
- [ ] Emerging rule: ≥ 5 messages in 10 sim-minutes → `emerging=true`, auto-call verify
- [ ] `POST /rumors/{id}/verify` → `verify` → write rumor verdict/evidence + draft outbound
- [ ] Individual reply on inbound: auto-send if `auto_send_ok`, else holding reply + queue for Dana
- [ ] `POST /outbound/{id}/approve` and `/edit`; simulated delivery (`sent` → `delivered`/`failed`, failure off by default)
- [ ] `POST /reset` calls P4's `seed.py`

**Loop + chaos**
- [ ] All 6 chaos endpoints (rumor wave reads P4's `rumors.json`)
- [ ] `rumor_loop.py`: after send → `monitoring`; compare next 2 windows of 10 sim-minutes → `resolved` (≥ 50% drop) or `reopened` (+ request a follow-up draft)
- [ ] Evidence expiring during monitoring → `evidence_expired=true`
- [ ] `shelter_a_full` marks any sent clarification about SH-A as `outdated`

### P2 — AI + safety
**Bedrock**
- [ ] Model access enabled; one Converse call works (v3 §0)
- [ ] Ask a mentor the Bedrock Agents question (v3 §0); post the answer in chat
- [ ] Decide on tooling (§3.5) and add the Step 1 / Step 2 tool JSON schemas to `backend/prompts/`

**Pipeline**
- [ ] `extract()`: system prompt with v3 §4 prompt rules; message text wrapped as data (e.g. `<resident_message>` tags)
- [ ] Code check in `extract()`: drop unknown entity IDs; match an existing cluster or propose a new claim
- [ ] `verify()`: pass structured shelter rows, bulletins with all timestamps + source authority, and `sim_clock`
- [ ] Follow-up draft for reopened rumors ("re-send with shelter manager confirmation")

**Validator (safety core)**
- [ ] `validator.py` implements every rule in v3 §5: IDs exist, exact address match, authority ≤ 2 non-expired for confirmed/contradicted, all evidence expired → "can't confirm", equal-authority conflict → flag for officer, higher authority wins if not expired, "as of HH:MM" appended, 300-char cap + "reply MORE"
- [ ] Regenerate once on reject, then fall back to `templates.py`
- [ ] `auto_send_ok` per v3 §5 "what sends automatically"
- [ ] All of P4's tests in `tests/` pass
- [ ] The prompt-injection text produces a normal answer, not "all shelters are closed"
- [ ] Per-step latency included in the output so P1 can put it in the trace

**Stretch:** Step 3 translation, with a check that numbers, times, IDs and addresses are preserved.

### P3 — Frontend
**Screen (v3 §8)**
- [ ] Vite + React scaffold
- [ ] Polling hook: `GET /state` every 2 s; env var switches mock ↔ live
- [ ] Status banner: **SIMULATION** label, sim clock, city site status, cache age
- [ ] Incoming feed with cluster tags
- [ ] Emerging Rumor card: verdict, evidence (published / verified / expires), draft, **Edit** + **Approve & send**
- [ ] Rumor status chips: monitoring / resolved ✅ / reopened ⚠️ / evidence expired, plus "Needs officer decision" and "outdated" badges
- [ ] Rate sparkline on the rumor card
- [ ] Resident phone sim: type, post to `/sms/inbound`, show the reply bubble
- [ ] Outbound log with state transitions (draft → approved → sent → delivered/failed)
- [ ] Chaos bar wired to all 6 endpoints + a Reset button
- [ ] Pipeline trace strip (Step1 ✓ Step2 ✓ Val ✓, with ms + detail on hover)
- [ ] Ages shown everywhere ("as of 04:10 · 25 min old")

**Ship**
- [ ] Deployed to Amplify Hosting or S3
- [ ] Readable at 1080p for the screen recording

### P4 — Data, QA, story
**Data**
- [ ] `frontend/src/mock/state.json` matching §3.3 (realistic, including an emerging rumor and expired evidence)
- [ ] `seed/data/*.json` per v3 §10: 5 sources, 4 shelters (made-up addresses), 3 zones, 6 bulletins incl. one superseded
- [ ] `seed/scripts/rumors.json`: 12 "Shelter A closed", 8 "tap water poisoned", 4 unrelated, 1 prompt injection
- [ ] `seed.py` loads everything into DynamoDB (P1 calls it from `/reset`)

**Tests**
- [ ] `tests/test_validator.py` + fixtures: one case per v3 §5 rule (expired evidence, equal-authority conflict, bad address, fake shelter ID, over-length text, missing "as of")
- [ ] `tests/test_pipeline.py`: golden inputs for Step 1 clustering (do the 12 variants land in one cluster?) and the injection text
- [ ] End-to-end manual run once the API is live; file bugs as issues tagged with the owner
- [ ] Every chaos button checked against the "what judges see" column in v3 §9

**Story**
- [ ] `demo/script.md`: exact clicks + exact texts to type for the 5-minute video (v3 §12)
- [ ] `demo/qa-prep.md` from v3 §13, with who answers which judge question
- [ ] Lead rehearsal, record 2–3 takes, edit, **upload to Box and confirm it's visible**

---

## 6. Dependencies (what each person consumes, and the fallback)

| Consumer | Needs | From | Until it exists, use |
|---|---|---|---|
| P3 | `/state` + endpoints | P1 | `mock/state.json` (P4) |
| P3 | Mock `/state` | P4 | Hand-write a minimal one from §3.3 |
| P1 | `extract()` / `verify()` | P2 | `pipeline_stub.py` |
| P1 | Seed data + rumor scripts | P4 | A few hand-written rows |
| P2 | Fixtures + tests | P4 | Rows copied from v3 §3 examples |
| P4 | Live API for QA | P1 | Test validator/pipeline offline; write demo script from v3 |

## 7. Shared milestones (in order, no deadlines)
1. **Contract agreed** (§3) and one Bedrock call works.
2. **First integration:** a typed text shows up clustered on screen.
3. **Full loop works once** (ugly is fine).
4. **All 6 chaos buttons work.**
5. **Demo runs twice without errors** → only then pick up stretch goals.
6. **Feature freeze** → bug fixes only, record video, upload to Box.
