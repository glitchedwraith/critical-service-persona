"""Chaos endpoints that mutate state to drive the demo (plan.md §5 phase 5,
v3 §9). Dispatched from app.py's POST /chaos/{action} route."""
import json

import clock
import db


def apply(action, body):
    """Dispatch to the named chaos action. Raises ValueError on unknown action
    or missing required args."""
    body = body or {}
    fn = _ACTIONS.get(action)
    if fn is None:
        raise ValueError(f"unknown chaos action: {action!r}")
    return fn(body)


def _city_site_down(_body):
    db.update("TABLE_SYSTEM", clock.SYSTEM_ID, {"city_site_online": False})
    return {"ok": True, "action": "city_site_down", "city_site_online": False}


def _rumor_wave(_body):
    """Inject 12 'Shelter A closed' variants across the three zones. These
    messages all go through the real /sms/inbound pipeline, so they cluster,
    bump rate_per_10min, and trip the emerging rule."""
    import app  # lazy
    injected = []
    for msg in _WAVE_MESSAGES:
        resp = app.lambda_handler({
            "routeKey": "POST /sms/inbound",
            "body": json.dumps(msg),
            "pathParameters": None,
        }, None)
        injected.append(json.loads(resp["body"]).get("message_id"))
    return {"ok": True, "action": "rumor_wave",
            "injected": len(injected), "message_ids": injected}


def _shelter_a_full(_body):
    """Authority-2 shelter-manager report: SH-A is full. Also marks any
    already-sent SH-A clarification as outdated=true."""
    db.put("TABLE_SOURCES", {
        "id": "SRC-MGR-A", "name": "Shelter A manager", "authority": 2,
    })
    now = clock.now()
    expires = clock.fmt(clock.parse(now) + 60)
    db.update("TABLE_SHELTERS", "SH-A", {
        "status": "full",
        "status_source_id": "SRC-MGR-A",
        "status_updated_at": now,
        "status_expires_at": expires,
    })
    outdated = []
    for rumor in db.scan("TABLE_RUMORS"):
        if "SH-A" not in (rumor.get("entity_ids") or []):
            continue
        cid = rumor.get("clarification_id")
        if not cid:
            continue
        outbound = db.get("TABLE_OUTBOUND", cid)
        if (outbound
                and outbound.get("kind") == "clarification"
                and outbound.get("state") in ("sent", "delivered")):
            db.update("TABLE_OUTBOUND", cid, {"outdated": True})
            outdated.append(cid)
    return {"ok": True, "action": "shelter_a_full",
            "outdated_clarifications": outdated}


def _conflicting_report(_body):
    """Authority-4 resident message claiming Shelter D is closed. Routed
    through /sms/inbound so it clusters/replies like any other inbound."""
    import app  # lazy
    resp = app.lambda_handler({
        "routeKey": "POST /sms/inbound",
        "body": json.dumps({
            "from": "+1-555-9999",
            "role": "resident",
            "zone": "B",
            "text": "shelter D is closed, saw it myself",
        }),
        "pathParameters": None,
    }, None)
    return {"ok": True, "action": "conflicting_report",
            "inbound": json.loads(resp["body"])}


def _advance_clock(body):
    minutes = int(body.get("minutes", 10))
    new_time = clock.advance(minutes)
    import rumor_loop  # lazy
    transitions = rumor_loop.tick()
    return {
        "ok": True, "action": "advance_clock",
        "sim_clock": new_time, "advanced_by_min": minutes,
        "transitions": [
            {"rumor_id": rid, "status": st, "follow_up_outbound_id": fu}
            for rid, st, fu in transitions
        ],
    }


def _expire_bulletin(body):
    bulletin_id = body.get("id")
    if not bulletin_id:
        raise ValueError("expire_bulletin requires {id: ...}")
    bulletin = db.get("TABLE_BULLETINS", bulletin_id)
    if bulletin is None:
        raise ValueError(f"bulletin {bulletin_id!r} not found")
    now = clock.now()
    expired_at = clock.fmt(clock.parse(now) - 1)
    db.update("TABLE_BULLETINS", bulletin_id, {
        "expires_at": expired_at,
        "status": "expired",
    })
    return {"ok": True, "action": "expire_bulletin",
            "bulletin_id": bulletin_id, "expires_at": expired_at}


_ACTIONS = {
    "city_site_down": _city_site_down,
    "rumor_wave": _rumor_wave,
    "shelter_a_full": _shelter_a_full,
    "conflicting_report": _conflicting_report,
    "advance_clock": _advance_clock,
    "expire_bulletin": _expire_bulletin,
}


# Inline fallback until P4 ships seed/scripts/rumors.json bundled with the
# Lambda. 12 variants of "Shelter A closed" across zones A, B, C.
_WAVE_MESSAGES = [
    {"from": f"+1-555-07{i:02d}", "role": "resident", "zone": zone, "text": text}
    for i, (zone, text) in enumerate([
        ("A", "hearing shelter A closed??"),
        ("B", "shelter A is shut, go to D"),
        ("B", "is shelter A really closed"),
        ("C", "SHELTER A CLOSED everyone move to D"),
        ("A", "shelter a shut down please confirm"),
        ("B", "my cousin says shelter A closed"),
        ("B", "shelter A closed???"),
        ("C", "they shut shelter A for repairs"),
        ("A", "shelter A closed, going to D"),
        ("B", "shelter A closing - true?"),
        ("B", "shelter a was shut earlier"),
        ("C", "shelter A closed and D is full too?"),
    ])
]
