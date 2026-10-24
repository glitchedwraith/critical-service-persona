"""Chaos endpoints that mutate state to drive the demo (plan.md §5 phase 5,
v3 §9). Dispatched from app.py's POST /chaos/{action} route.

All demo content (resident texts, guided situations) comes from P4's seed
package (backend/seed/); nothing here hard-codes message text.
"""
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


def _require(body, *keys):
    missing = [k for k in keys if body.get(k) in (None, "")]
    if missing:
        raise ValueError(f"missing fields: {missing}")


# ---- system ----------------------------------------------------------------

def _city_site(body):
    """{online: bool}; omit to toggle."""
    system = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
    online = body.get("online")
    if online is None:
        online = not bool(system.get("city_site_online"))
    db.update("TABLE_SYSTEM", clock.SYSTEM_ID, {"city_site_online": bool(online)})
    return {"ok": True, "action": "city_site", "city_site_online": bool(online)}


def _city_site_down(_body):
    return _city_site({"online": False})


def _delivery_fail(body):
    """{on: bool}. Outbound sent while on is marked `failed` instead of
    `delivered` by the lazy delivery sim."""
    on = bool(body.get("on", True))
    db.update("TABLE_SYSTEM", clock.SYSTEM_ID, {"delivery_fail_mode": on})
    return {"ok": True, "action": "delivery_fail", "delivery_fail_mode": on}


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


# ---- resident traffic ------------------------------------------------------

def _run_script(body):
    """{script}: push each scripted message through the real /sms/inbound
    route, so it clusters, bumps rates and trips the emerging rule."""
    _require(body, "script")
    from seed import seed as seed_mod  # lazy
    script = seed_mod.scripts().get(body["script"])
    if script is None:
        raise ValueError(f"unknown script: {body['script']!r}")
    import app  # lazy
    injected = []
    for msg in script["messages"]:
        resp = app.lambda_handler({
            "routeKey": "POST /sms/inbound",
            "body": json.dumps(msg),
            "pathParameters": None,
        }, None)
        injected.append(json.loads(resp["body"]).get("message_id"))
    return {"ok": True, "action": "run_script", "script": body["script"],
            "injected": len(injected), "message_ids": injected}


def _rumor_wave(_body):
    return _run_script({"script": "shelter_a_wave"})


def _conflicting_report(_body):
    return _run_script({"script": "conflicting_report"})


# ---- official data ---------------------------------------------------------

def _shelter_status(body):
    """{shelter_id, source_id, status}: an official report changes a shelter.
    Any already-sent clarification about that shelter becomes outdated."""
    _require(body, "shelter_id", "source_id", "status")
    sid = body["shelter_id"]
    shelter = db.get("TABLE_SHELTERS", sid)
    if shelter is None:
        raise ValueError(f"shelter {sid!r} not found")
    if db.get("TABLE_SOURCES", body["source_id"]) is None:
        raise ValueError(f"source {body['source_id']!r} not found")
    now = clock.now()
    updates = {
        "status": body["status"],
        "status_source_id": body["source_id"],
        "status_updated_at": now,
        "status_expires_at": clock.fmt(clock.parse(now) + 60),
    }
    if body["status"] == "full":
        updates["occupancy"] = shelter.get("capacity", 0)
    db.update("TABLE_SHELTERS", sid, updates)
    return {"ok": True, "action": "shelter_status", "shelter_id": sid,
            "outdated_clarifications": _mark_outdated(sid)}


def _shelter_a_full(_body):
    return _shelter_status({"shelter_id": "SH-A", "source_id": "SRC-MGR-A",
                            "status": "full"})


def _mark_outdated(shelter_id):
    outdated = []
    for rumor in db.scan("TABLE_RUMORS"):
        if shelter_id not in (rumor.get("entity_ids") or []):
            continue
        cid = rumor.get("clarification_id")
        outbound = db.get("TABLE_OUTBOUND", cid) if cid else None
        if (outbound
                and outbound.get("kind") == "clarification"
                and outbound.get("state") in ("sent", "delivered")):
            db.update("TABLE_OUTBOUND", cid, {"outdated": True})
            db.update("TABLE_RUMORS", rumor["id"], {"outdated": True})
            outdated.append(cid)
    return outdated


def _conflict_report(body):
    """{shelter_id, source_id, status}: a second source reports a different
    status without overwriting the row. If its authority equals the current
    status source, the validator flags it for the officer."""
    _require(body, "shelter_id", "source_id", "status")
    if db.get("TABLE_SHELTERS", body["shelter_id"]) is None:
        raise ValueError(f"shelter {body['shelter_id']!r} not found")
    db.update("TABLE_SHELTERS", body["shelter_id"], {"conflict": {
        "source_id": body["source_id"],
        "status": body["status"],
        "reported_at": clock.now(),
    }})
    return {"ok": True, "action": "conflict_report",
            "shelter_id": body["shelter_id"]}


def _officer_decision(body):
    """{shelter_id, source_id}: Dana picks which source to trust. Clears the
    conflict, applies the chosen status and re-verifies affected rumors."""
    _require(body, "shelter_id", "source_id")
    shelter = db.get("TABLE_SHELTERS", body["shelter_id"])
    if shelter is None or not shelter.get("conflict"):
        raise ValueError(f"no open conflict on {body['shelter_id']!r}")
    conflict = shelter["conflict"]
    now = clock.now()
    status = (conflict["status"] if body["source_id"] == conflict["source_id"]
              else shelter.get("status"))
    db.update("TABLE_SHELTERS", body["shelter_id"], {
        "status": status,
        "status_source_id": body["source_id"],
        "status_updated_at": now,
        "status_expires_at": clock.fmt(clock.parse(now) + 60),
        "conflict": None,
    })
    reverified = _reverify(lambda r: body["shelter_id"] in (r.get("entity_ids") or []))
    return {"ok": True, "action": "officer_decision", "status": status,
            "reverified": reverified}


def _expire_bulletin(body):
    _require(body, "id")
    bulletin = db.get("TABLE_BULLETINS", body["id"])
    if bulletin is None:
        raise ValueError(f"bulletin {body['id']!r} not found")
    expired_at = clock.fmt(clock.parse(clock.now()) - 1)
    db.update("TABLE_BULLETINS", body["id"], {
        "expires_at": expired_at,
        "status": "expired",
    })
    return {"ok": True, "action": "expire_bulletin",
            "bulletin_id": body["id"], "expires_at": expired_at}


def _expire_shelter(body):
    """{id}: the shelter's status passes its review deadline."""
    _require(body, "id")
    if db.get("TABLE_SHELTERS", body["id"]) is None:
        raise ValueError(f"shelter {body['id']!r} not found")
    expired_at = clock.fmt(clock.parse(clock.now()) - 1)
    db.update("TABLE_SHELTERS", body["id"], {"status_expires_at": expired_at})
    return {"ok": True, "action": "expire_shelter",
            "shelter_id": body["id"], "status_expires_at": expired_at}


# ---- verification ----------------------------------------------------------

def _reverify(predicate):
    import app  # lazy
    done = []
    for rumor in db.scan("TABLE_RUMORS"):
        if rumor.get("status") == "resolved" or not rumor.get("emerging"):
            continue
        if predicate(rumor):
            app._verify_rumor(rumor["id"])
            done.append(rumor["id"])
    return done


def _verify_entity(body):
    """{entity_id}: verify open rumors about an entity, even below the
    emerging threshold (used when official sources change mid-incident)."""
    _require(body, "entity_id")
    import app  # lazy
    entity_id = body["entity_id"]
    matching = [
        rumor for rumor in db.scan("TABLE_RUMORS")
        if rumor.get("status") != "resolved"
           and entity_id in (rumor.get("entity_ids") or [])
    ]

    # A correction in any of these states already represents this entity's
    # incident. Do not create another outbound message for another rumor row.
    active_states = {"draft", "sent", "delivered", "failed"}
    active_rumor_ids = {
        outbound.get("rumor_id")
        for outbound in db.scan("TABLE_OUTBOUND")
        if outbound.get("kind") == "clarification"
           and outbound.get("state") in active_states
           and outbound.get("rumor_id")
    }
    already_covered = any(r.get("id") in active_rumor_ids for r in matching)
    done = []
    skipped = []
    for rumor in matching:
        if already_covered:
            skipped.append(rumor["id"])
            continue
        app._verify_rumor(rumor["id"])
        done.append(rumor["id"])
        # The first verification creates a draft; subsequent rumor rows for
        # the same entity must not create duplicate drafts.
        already_covered = True
    return {"ok": True, "action": "verify_entity",
            "verified": done, "skipped_duplicates": skipped}


def _reverify_open(_body):
    """Re-run Step 2 on every open emerging rumor (e.g. after expiry)."""
    return {"ok": True, "action": "reverify_open",
            "verified": _reverify(lambda _r: True)}


# ---- guided situations -----------------------------------------------------

def _situation(body):
    """{id}: run a P4 situation (seed/data/situations.json) step by step.
    Progress is written to system.active_situation so every screen can
    stream the same narration."""
    _require(body, "id")
    from seed import seed as seed_mod  # lazy
    sit = next((s for s in seed_mod.situations() if s["id"] == body["id"]), None)
    if sit is None:
        raise ValueError(f"unknown situation: {body['id']!r}")

    # check for repeats
    system_before = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
    if sit["id"] in (system_before.get("situations_done") or []):
        return {"ok": True, "action": "situation", "id": sit["id"],
                "already_completed": True, "steps": []}

    active = {"id": sit["id"], "title": sit["title"],
              "narration": sit["narration"], "running": True}
    db.update("TABLE_SYSTEM", clock.SYSTEM_ID, {"active_situation": active})
    results = []
    try:
        for step in sit["steps"]:
            if step["action"] == "situation":
                raise ValueError("situations cannot nest")
            results.append(apply(step["action"], step.get("body") or {}))
    finally:
        system = db.get("TABLE_SYSTEM", clock.SYSTEM_ID) or {}
        done = list(system.get("situations_done") or [])
        if sit["id"] not in done:
            done.append(sit["id"])
        db.update("TABLE_SYSTEM", clock.SYSTEM_ID, {
            "active_situation": dict(active, running=False),
            "situations_done": done,
        })
    return {"ok": True, "action": "situation", "id": sit["id"],
            "steps": results}


_ACTIONS = {
    "city_site": _city_site,
    "city_site_down": _city_site_down,
    "delivery_fail": _delivery_fail,
    "advance_clock": _advance_clock,
    "run_script": _run_script,
    "rumor_wave": _rumor_wave,
    "conflicting_report": _conflicting_report,
    "shelter_status": _shelter_status,
    "shelter_a_full": _shelter_a_full,
    "conflict_report": _conflict_report,
    "officer_decision": _officer_decision,
    "expire_bulletin": _expire_bulletin,
    "expire_shelter": _expire_shelter,
    "verify_entity": _verify_entity,
    "reverify_open": _reverify_open,
    "situation": _situation,
}
