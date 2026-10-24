"""Lambda entry point and HTTP route dispatch.

Route contract: plan.md §3.2. State response shape: plan.md §3.3.
"""
import json
import time
from decimal import Decimal

import clock
import db
import pipeline_stub as pipeline  # Phase 6 swap: `import pipeline as pipeline`
import validator_stub as validator  # Phase 6 swap: `import validator as validator`


DELIVERY_DELAY_SEC = 2  # sent -> delivered promotion threshold (wall-clock seconds)


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    path_params = event.get("pathParameters") or {}
    body = _parse_body(event)
    try:
        handler = ROUTES.get(route)
        if handler is None:
            return _respond(404, {"error": f"no handler for {route!r}"})
        return handler(path_params, body)
    except KeyError as e:
        return _respond(500, {"error": f"missing env var or key: {e}"})
    except Exception as e:
        return _respond(500, {"error": str(e), "type": type(e).__name__})


# ---- GET /state ------------------------------------------------------------

def _handle_state(_path, _body):
    _promote_delivered()
    system = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
    sim_clock = system.get("sim_clock") or "00:00"

    bulletins = [_bulletin_flags(b, sim_clock) for b in db.scan("TABLE_BULLETINS")]
    shelters = [_shelter_flags(s, sim_clock) for s in db.scan("TABLE_SHELTERS")]
    rumors = [_rumor_flags(r, sim_clock) for r in db.scan("TABLE_RUMORS")]
    messages = sorted(
        db.scan("TABLE_MESSAGES"),
        key=lambda m: m.get("received_at") or "",
        reverse=True,
    )[:50]
    outbound = sorted(
        db.scan("TABLE_OUTBOUND"),
        key=lambda o: o.get("created_at") or o.get("approved_at") or "",
        reverse=True,
    )
    trace = list(reversed(system.get("trace") or []))[:50]

    return _respond(200, {
        "system": {
            "sim_clock": system.get("sim_clock"),
            "city_site_online": system.get("city_site_online"),
            "approver": system.get("approver"),
            "cache_as_of": system.get("cache_as_of"),
        },
        "messages": messages,
        "rumors": rumors,
        "outbound": outbound,
        "shelters": shelters,
        "bulletins": bulletins,
        "trace": trace,
    })


def _bulletin_flags(b, now):
    out = dict(b)
    status = b.get("status") or "active"
    expires = b.get("expires_at")
    published = b.get("published_at")
    out["expired"] = status in ("expired", "superseded") or _ts_lt(expires, now)
    out["age_min"] = (
        clock.minutes_between(published, now) if published else None
    )
    return out


def _shelter_flags(s, now):
    out = dict(s)
    out["expired"] = _ts_lt(s.get("status_expires_at"), now)
    return out


def _rumor_flags(r, now):
    out = dict(r)
    out["emerging"] = bool(r.get("emerging")) or _rate_is_emerging(r.get("rate_per_10min"))
    out["outdated"] = bool(r.get("outdated"))
    out["evidence_expired"] = any(
        _ts_lt(e.get("expires_at"), now)
        for e in (r.get("evidence") or [])
    )
    return out


def _rate_is_emerging(rate):
    if not rate:
        return False
    return int(rate[-1]) >= 5


def _promote_delivered():
    """Lazy delivery sim: sent -> delivered after DELIVERY_DELAY_SEC wall seconds."""
    now_wall = time.time()
    for o in db.scan("TABLE_OUTBOUND"):
        if o.get("state") != "sent":
            continue
        sent_wall = o.get("sent_at_wall")
        if sent_wall is None:
            continue
        if (now_wall - float(sent_wall)) >= DELIVERY_DELAY_SEC:
            db.update("TABLE_OUTBOUND", o["id"], {
                "state": "delivered",
                "delivered_at": clock.now(),
            })


def _ts_lt(a, b):
    """Fixed-width 'HH:MM' lex-compare is a valid < within one sim day."""
    return a is not None and b is not None and a < b


# ---- POST /sms/inbound -----------------------------------------------------

def _handle_inbound(_path, body):
    if not isinstance(body, dict):
        return _respond(400, {"error": "body must be a JSON object"})
    missing = [k for k in ("from", "role", "zone", "text") if k not in body]
    if missing:
        return _respond(400, {"error": f"missing fields: {missing}"})

    now = clock.now()
    msg_id = _next_id("M")
    message = {
        "id": msg_id,
        "from": body["from"],
        "role": body["role"],
        "zone": body["zone"],
        "text": body["text"],
        "received_at": now,
        "claims": [],
        "cluster_id": None,
        "reply_id": None,
    }
    db.put("TABLE_MESSAGES", message)

    rumors = db.scan("TABLE_RUMORS")
    shelters = db.scan("TABLE_SHELTERS")
    bulletins = db.scan("TABLE_BULLETINS")
    sources = db.scan("TABLE_SOURCES")
    active_clusters = [{"id": r["id"], "claim": r.get("claim", "")}
                       for r in rumors if r.get("status") != "resolved"]
    entity_ids = [s["id"] for s in shelters]

    # Step 1
    t0 = time.time()
    step1 = pipeline.extract(body["text"], active_clusters, entity_ids)
    step1_ms = int((time.time() - t0) * 1000)

    cluster_id, emerging_fired = _apply_clustering(step1, now)

    _append_trace(
        step="step1",
        ok=True,
        detail=(f"cluster={cluster_id}" if cluster_id
                else f"type={step1.get('question_type')}"),
        ms=step1_ms,
        message_id=msg_id,
    )

    msg_updates = {
        "claims": [c["text"] for c in step1.get("claims") or []],
        "cluster_id": cluster_id,
    }

    reply = None
    if step1.get("question_type") in ("status_question", "rumor"):
        reply = _draft_individual_reply(
            msg_id, body["from"], cluster_id, now,
            shelters, bulletins, sources,
        )
        if reply:
            msg_updates["reply_id"] = reply["id"]

    db.update("TABLE_MESSAGES", msg_id, msg_updates)

    if emerging_fired and cluster_id:
        _verify_rumor(cluster_id, msg_id)

    return _respond(200, {
        "message_id": msg_id,
        "cluster_id": cluster_id,
        "reply": reply,
    })


def _apply_clustering(step1, now):
    """Match or create a rumor cluster. Returns (cluster_id, emerging_fired)."""
    cluster_id = None
    emerging_fired = False

    if step1.get("cluster_match"):
        rumor = db.get("TABLE_RUMORS", step1["cluster_match"])
        if rumor:
            cluster_id = rumor["id"]
            new_rate = _bump_rate(rumor, now)
            new_count = int(rumor.get("message_count", 0)) + 1
            db.update("TABLE_RUMORS", cluster_id, {
                "message_count": new_count,
                "rate_per_10min": new_rate,
            })
            if not rumor.get("emerging") and _emerging_rule(new_rate):
                emerging_fired = True

    if cluster_id is None and step1.get("new_cluster_claim"):
        cluster_id = _next_id("R")
        entity_ids = (step1["claims"][0]["entity_ids"]
                      if step1.get("claims") else [])
        db.put("TABLE_RUMORS", {
            "id": cluster_id,
            "claim": step1["new_cluster_claim"],
            "entity_ids": entity_ids,
            "message_count": 1,
            "rate_per_10min": [1],
            "first_seen": now,
            "status": "new",
            "verdict": "unverified",
            "evidence": [],
            "emerging": False,
        })

    return cluster_id, emerging_fired


def _emerging_rule(rate):
    """≥5 messages in a sliding ~10 sim-min window. Current bucket plus spillover."""
    if not rate:
        return False
    window = rate[-2:] if len(rate) >= 2 else rate[-1:]
    return sum(int(x) for x in window) >= 5


def _bump_rate(rumor, now_str):
    first_seen = rumor.get("first_seen") or now_str
    delta = clock.parse(now_str) - clock.parse(first_seen)
    idx = max(delta // 10, 0)
    rate = [int(x) for x in (rumor.get("rate_per_10min") or [])]
    while len(rate) <= idx:
        rate.append(0)
    rate[idx] += 1
    return rate


def _draft_individual_reply(msg_id, to, cluster_id, now, shelters, bulletins, sources):
    """Run pipeline.verify for the individual response. Auto-send or holding reply."""
    rumor = db.get("TABLE_RUMORS", cluster_id) if cluster_id else {}

    t0 = time.time()
    result = pipeline.verify(rumor or {}, shelters, bulletins, sources, now)
    ms = int((time.time() - t0) * 1000)

    validator = result.get("validator") or {}
    passed = bool(validator.get("passed"))
    auto_ok = bool(result.get("auto_send_ok"))

    outbound_id = _next_id("O")
    if passed and auto_ok:
        text = result.get("reply_text") or ""
    else:
        text = f"We're checking. Last official update: {now} (City EOC)."

    outbound = {
        "id": outbound_id,
        "kind": "reply",
        "to": to,
        "lang": "en",
        "text": text,
        "source_ids": [e["source_id"] for e in result.get("evidence") or []],
        "valid_until": _max_expires(result.get("evidence")),
        "state": "sent",
        "created_at": now,
        "sent_at_wall": int(time.time()),
        "approved_by": None,
        "approved_at": None,
        "message_id": msg_id,
    }
    db.put("TABLE_OUTBOUND", outbound)

    _append_trace(step="step2", ok=passed,
                  detail=f"reply {outbound_id}", ms=ms, message_id=msg_id)
    _append_trace(step="send", ok=True,
                  detail=f"to {to} ({'auto' if passed and auto_ok else 'hold'})",
                  ms=0, message_id=msg_id)
    return outbound


def _verify_rumor(rumor_id, trigger_msg_id=None):
    """Run pipeline.verify, persist evidence + validator meta on the rumor,
    and create a broadcast draft outbound. Returns (rumor, outbound) or
    (None, None) if the rumor id is unknown."""
    rumor = db.get("TABLE_RUMORS", rumor_id)
    if not rumor:
        return None, None
    shelters = db.scan("TABLE_SHELTERS")
    bulletins = db.scan("TABLE_BULLETINS")
    sources = db.scan("TABLE_SOURCES")
    now = clock.now()

    t0 = time.time()
    result = pipeline.verify(rumor, shelters, bulletins, sources, now)
    ms = int((time.time() - t0) * 1000)

    outbound_id = _next_id("O")
    outbound = {
        "id": outbound_id,
        "kind": "clarification",
        "to": "zone:all",
        "lang": "en",
        "text": result.get("clarification_text") or "",
        "source_ids": [e["source_id"] for e in result.get("evidence") or []],
        "valid_until": _max_expires(result.get("evidence")),
        "state": "draft",
        "created_at": now,
        "approved_by": None,
        "approved_at": None,
        "rumor_id": rumor_id,
        "validator": result.get("validator"),
        "auto_send_ok": bool(result.get("auto_send_ok")),
    }
    db.put("TABLE_OUTBOUND", outbound)

    validator_meta = result.get("validator") or {}
    db.update("TABLE_RUMORS", rumor_id, {
        "verdict": result.get("verdict", "unverified"),
        "current_status_known": bool(result.get("current_status_known")),
        "evidence": result.get("evidence") or [],
        "clarification_id": outbound_id,
        "emerging": True,
        "status": "drafted",
        "validator": {
            "passed": bool(validator_meta.get("passed")),
            "flags": validator_meta.get("flags") or [],
            "fallback_used": bool(validator_meta.get("fallback_used")),
        },
        "auto_send_ok": bool(result.get("auto_send_ok")),
    })

    _append_trace(step="step2", ok=True,
                  detail=f"verified {rumor_id} -> draft {outbound_id}",
                  ms=ms, message_id=trigger_msg_id)
    _append_trace(step="validator", ok=bool(validator_meta.get("passed")),
                  detail=f"flags={validator_meta.get('flags') or []}",
                  ms=0, message_id=trigger_msg_id)
    return db.get("TABLE_RUMORS", rumor_id), outbound


def _max_expires(evidence):
    exps = [e.get("expires_at") for e in (evidence or []) if e.get("expires_at")]
    return max(exps) if exps else None


# ---- POST /rumors/{id}/verify ---------------------------------------------

def _handle_verify(path, _body):
    rumor_id = (path or {}).get("id")
    if not rumor_id:
        return _respond(400, {"error": "missing path param id"})
    rumor, outbound = _verify_rumor(rumor_id)
    if rumor is None:
        return _respond(404, {"error": f"rumor {rumor_id!r} not found"})
    return _respond(200, {
        "rumor": _rumor_flags(rumor, clock.now()),
        "outbound": outbound,
    })


# ---- POST /outbound/{id}/edit ---------------------------------------------

def _handle_edit(path, body):
    outbound_id = (path or {}).get("id")
    if not outbound_id:
        return _respond(400, {"error": "missing path param id"})
    if not isinstance(body, dict) or "text" not in body:
        return _respond(400, {"error": "body must be {text: ...}"})

    outbound = db.get("TABLE_OUTBOUND", outbound_id)
    if outbound is None:
        return _respond(404, {"error": f"outbound {outbound_id!r} not found"})
    if outbound.get("state") != "draft":
        return _respond(400, {
            "error": f"cannot edit outbound in state {outbound.get('state')!r}; "
                     "only drafts are editable"
        })

    new_text = body["text"]
    ctx = {
        "shelters": db.scan("TABLE_SHELTERS"),
        "bulletins": db.scan("TABLE_BULLETINS"),
        "sources": db.scan("TABLE_SOURCES"),
        "sim_clock": clock.now(),
    }
    fixed_draft, flags = validator.validate(dict(outbound, text=new_text), ctx)
    db.update("TABLE_OUTBOUND", outbound_id, {
        "text": fixed_draft.get("text", new_text),
        "validator": {
            "passed": not flags,
            "flags": flags,
            "fallback_used": False,
        },
    })
    _append_trace(step="validator", ok=not flags,
                  detail=f"edit {outbound_id}", ms=0, message_id=None)
    return _respond(200, db.get("TABLE_OUTBOUND", outbound_id))


# ---- POST /outbound/{id}/approve ------------------------------------------

def _handle_approve(path, body):
    outbound_id = (path or {}).get("id")
    if not outbound_id:
        return _respond(400, {"error": "missing path param id"})
    if not isinstance(body, dict) or "approver" not in body:
        return _respond(400, {"error": "body must be {approver: ...}"})

    outbound = db.get("TABLE_OUTBOUND", outbound_id)
    if outbound is None:
        return _respond(404, {"error": f"outbound {outbound_id!r} not found"})
    if outbound.get("state") != "draft":
        return _respond(400, {
            "error": f"only drafts can be approved; got state={outbound.get('state')!r}"
        })

    now = clock.now()
    db.update("TABLE_OUTBOUND", outbound_id, {
        "state": "sent",
        "approved_by": body["approver"],
        "approved_at": now,
        "sent_at_wall": int(time.time()),
    })

    rumor_id = outbound.get("rumor_id")
    if rumor_id:
        rumor = db.get("TABLE_RUMORS", rumor_id)
        if rumor:
            db.update("TABLE_RUMORS", rumor_id, {
                "status": "monitoring",
                "baseline_rate_per_10min": list(rumor.get("rate_per_10min") or []),
            })

    _append_trace(step="send", ok=True,
                  detail=f"approved {outbound_id} by {body['approver']}",
                  ms=0, message_id=None)
    return _respond(200, db.get("TABLE_OUTBOUND", outbound_id))


# ---- POST /reset -----------------------------------------------------------

def _handle_reset(_path, _body):
    seed_error = None
    try:
        from seed import seed as seed_mod  # P4's module; may not exist yet
        seed_mod.seed()
    except (ImportError, AttributeError) as e:
        seed_error = f"{type(e).__name__}: {e}"
    db.put("TABLE_SYSTEM", {
        "id": clock.SYSTEM_ID,
        "sim_clock": "04:30",
        "city_site_online": True,
        "approver": "Dana",
        "cache_as_of": "04:10",
        "trace": [],
    })
    return _respond(200, {
        "ok": True,
        "seed_imported": seed_error is None,
        "seed_error": seed_error,
    })


# ---- shared helpers --------------------------------------------------------

def _next_id(prefix):
    """Atomic increment on system singleton (DynamoDB ADD). Returns 'PREFIX-NNN'."""
    tbl = db.table("TABLE_SYSTEM")
    resp = tbl.update_item(
        Key={"id": clock.SYSTEM_ID},
        UpdateExpression="ADD #c :one",
        ExpressionAttributeNames={"#c": f"counter_{prefix}"},
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    n = int(resp["Attributes"][f"counter_{prefix}"])
    return f"{prefix}-{n:03d}"


def _append_trace(step, ok, detail, ms, message_id=None):
    entry = {
        "at": clock.now(),
        "message_id": message_id,
        "step": step,
        "ok": bool(ok),
        "detail": detail,
        "ms": int(ms),
    }
    db.append("TABLE_SYSTEM", clock.SYSTEM_ID, "trace", entry, max_len=50)


# ---- routing + response plumbing -------------------------------------------

ROUTES = {
    "GET /state": _handle_state,
    "POST /reset": _handle_reset,
    "POST /sms/inbound": _handle_inbound,
    "POST /rumors/{id}/verify": _handle_verify,
    "POST /outbound/{id}/edit": _handle_edit,
    "POST /outbound/{id}/approve": _handle_approve,
    # TODO(P1 phase 5): POST /chaos/{action}
}


def _parse_body(event):
    raw = event.get("body")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=_json_default),
    }


def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(f"not JSON-serializable: {type(o).__name__}")
