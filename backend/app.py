"""Lambda entry point and HTTP route dispatch.

Route contract: plan.md §3.2. State response shape: plan.md §3.3.
"""
import hashlib
import json
import time
from decimal import Decimal

import ai_status
import clock
import db
import pipeline  # real Bedrock pipeline (falls back to heuristics if offline)
import templates
import validator  # real validator (plan.md §5 rules)


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
    from seed import seed as seed_mod  # lazy; P4 data bundled in the Lambda
    situations = [{k: s[k] for k in ("id", "title", "narration")}
                  for s in seed_mod.situations()]

    return _respond(200, {
        "system": {
            "sim_clock": system.get("sim_clock"),
            "city_site_online": system.get("city_site_online"),
            "approver": system.get("approver"),
            "cache_as_of": system.get("cache_as_of"),
            "delivery_fail_mode": bool(system.get("delivery_fail_mode")),
            "active_situation": system.get("active_situation"),
            "situations_done": system.get("situations_done") or [],
            "demo_phone": system.get("demo_phone"),
            "ai": ai_status.status(),  # Bedrock credential health (additive)
        },
        "zones": sorted(db.scan("TABLE_ZONES"), key=lambda z: z["id"]),
        "sources": db.scan("TABLE_SOURCES"),
        "situations": situations,
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
            failed = bool(o.get("fail_on_delivery"))
            db.update("TABLE_OUTBOUND", o["id"], {
                "state": "failed" if failed else "delivered",
                "delivered_at": None if failed else clock.now(),
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
    lat, lng = _place_message(msg_id, body)
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
        "lat": lat,
        "lng": lng,
    }
    db.put("TABLE_MESSAGES", message)

    rumors = db.scan("TABLE_RUMORS")
    shelters = db.scan("TABLE_SHELTERS")
    bulletins = db.scan("TABLE_BULLETINS")
    sources = db.scan("TABLE_SOURCES")
    active_clusters = [{"id": r["id"], "claim": r.get("claim", "")}
                       for r in rumors if r.get("status") != "resolved"]
    # Bulletins are entities too, so non-shelter rumors (water) can be grounded.
    entity_labels = {s["id"]: s.get("name", "") for s in shelters}
    entity_labels.update({b["id"]: b.get("title", "") for b in bulletins
                          if b.get("status") == "active"})
    entity_ids = list(entity_labels)

    # Step 1
    t0 = time.time()
    step1 = pipeline.extract(body["text"], active_clusters, entity_ids,
                             entity_labels=entity_labels)
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
            shelters, bulletins, sources, step1,
        )
        if reply:
            msg_updates["reply_id"] = reply["id"]

    db.update("TABLE_MESSAGES", msg_id, msg_updates)

    if emerging_fired and cluster_id:
        _verify_rumor(cluster_id, msg_id)

    import rumor_loop  # lazy to avoid import cycle
    rumor_loop.tick()

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


def _draft_individual_reply(msg_id, to, cluster_id, now, shelters, bulletins,
                            sources, step1=None):
    """Run pipeline.verify for the individual response. Auto-send or holding reply."""
    rumor = db.get("TABLE_RUMORS", cluster_id) if cluster_id else None
    if not rumor:
        # Plain status question: verify the question's own claims.
        claims = (step1 or {}).get("claims") or []
        rumor = {
            "claim": "; ".join(c.get("text", "") for c in claims),
            "entity_ids": sorted({e for c in claims for e in c.get("entity_ids") or []}),
        }

    t0 = time.time()
    result = pipeline.verify(rumor or {}, shelters, bulletins, sources, now)
    ms = int((time.time() - t0) * 1000)

    validator = result.get("validator") or {}
    passed = bool(validator.get("passed"))
    auto_ok = bool(result.get("auto_send_ok"))

    outbound_id = _next_id("O")
    system = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
    if passed and auto_ok:
        text = result.get("reply_text") or ""
    else:
        text = templates.holding_reply(system.get("cache_as_of") or now)

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
        "fail_on_delivery": bool(system.get("delivery_fail_mode")),
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

    # Re-verifying replaces the pending draft instead of stacking a new one.
    prev = (db.get("TABLE_OUTBOUND", rumor["clarification_id"])
            if rumor.get("clarification_id") else None)
    outbound_id = (prev["id"] if prev and prev.get("state") == "draft"
                   else _next_id("O"))
    outbound = {
        "id": outbound_id,
        "kind": "clarification",
        "to": _target_zones(rumor_id),
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
        "outdated": False,
        "evidence_expired": False,
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


def _target_zones(rumor_id):
    """'zone:A,B' — the zones whose residents texted about this rumor."""
    zones = sorted({m.get("zone") for m in db.scan("TABLE_MESSAGES")
                    if m.get("cluster_id") == rumor_id and m.get("zone")})
    return "zone:" + (",".join(zones) or "all")


def _place_message(msg_id, body):
    """Map position for a message: explicit lat/lng, else the zone centroid
    plus a small deterministic jitter (keeps geo logic out of the UI)."""
    if body.get("lat") is not None and body.get("lng") is not None:
        return Decimal(str(body["lat"])), Decimal(str(body["lng"]))
    zone = db.get("TABLE_ZONES", body.get("zone") or "")
    if not zone or not zone.get("centroid"):
        return None, None
    h = hashlib.sha1(msg_id.encode()).digest()
    dlat = (h[0] / 255 - 0.5) * 0.012
    dlng = (h[1] / 255 - 0.5) * 0.016
    lat, lng = (float(x) for x in zone["centroid"])
    return Decimal(str(round(lat + dlat, 5))), Decimal(str(round(lng + dlng, 5)))


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
    system = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
    db.update("TABLE_OUTBOUND", outbound_id, {
        "state": "sent",
        "approved_by": body["approver"],
        "approved_at": now,
        "sent_at_wall": int(time.time()),
        "fail_on_delivery": bool(system.get("delivery_fail_mode")),
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


# ---- POST /chaos/{action} -------------------------------------------------

def _handle_chaos(path, body):
    action = (path or {}).get("action")
    if not action:
        return _respond(400, {"error": "missing path param action"})
    import chaos  # lazy
    try:
        result = chaos.apply(action, body)
    except ValueError as e:
        return _respond(400, {"error": str(e)})
    return _respond(200, result)


# ---- POST /reset -----------------------------------------------------------

def _handle_reset(_path, _body):
    """Truncate every table and reload P4's seed data (backend/seed/)."""
    from seed import seed as seed_mod
    counts = seed_mod.seed(clear=True)
    return _respond(200, {"ok": True, "seed_imported": True, "counts": counts})


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
    "POST /chaos/{action}": _handle_chaos,
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
