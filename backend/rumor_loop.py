"""Rumor resolution monitor. Runs on inbound and clock-advancing events.

Transitions per plan.md §5 phase 5 and TrueSignal-Plan-v3.md §6:
    monitoring -> resolved     when post-send rate drops >= 50%
    monitoring -> reopened     otherwise (also drafts a follow-up outbound)
    monitoring + evidence_expired=true when any evidence row expires
"""
import clock
import db


def tick():
    """Walk monitoring rumors and apply transitions. Returns a list of
    (rumor_id, new_status, follow_up_outbound_id)."""
    results = []
    now = clock.now()
    for rumor in db.scan("TABLE_RUMORS"):
        if rumor.get("status") != "monitoring":
            continue
        _flag_evidence_expired(rumor, now)
        transition, follow_up = _evaluate(rumor)
        if transition is not None:
            results.append((rumor["id"], transition, follow_up))
    return results


def _evaluate(rumor):
    """Return (new_status_or_None, follow_up_outbound_id_or_None).

    Treats missing post-send buckets as implicit zeros so a silent period
    after approve correctly transitions to resolved (not stuck in monitoring)."""
    first_seen = rumor.get("first_seen")
    if not first_seen:
        return None, None
    now = clock.now()
    virtual_len = (clock.parse(now) - clock.parse(first_seen)) // 10 + 1

    baseline = [int(x) for x in (rumor.get("baseline_rate_per_10min") or [])]
    current = [int(x) for x in (rumor.get("rate_per_10min") or [])]
    baseline_len = len(baseline)

    # Pad virtually with zeros so empty buckets count as "quiet".
    while len(current) < virtual_len:
        current.append(0)

    # Need at least two post-send 10-min buckets of (real or zero) data.
    if virtual_len < baseline_len + 2:
        return None, None

    post = sum(current[baseline_len:baseline_len + 2])
    pre_window = baseline[-2:] if len(baseline) >= 2 else baseline[-1:]
    pre = sum(pre_window)

    if pre == 0 or post * 2 < pre:  # post < 0.5 * pre, integer-safe
        db.update("TABLE_RUMORS", rumor["id"], {"status": "resolved"})
        return "resolved", None

    follow_up_id = _draft_follow_up(rumor["id"])
    db.update("TABLE_RUMORS", rumor["id"], {"status": "reopened"})
    return "reopened", follow_up_id


def _flag_evidence_expired(rumor, now):
    if rumor.get("evidence_expired"):
        return
    for e in (rumor.get("evidence") or []):
        exp = e.get("expires_at")
        if exp is not None and exp < now:
            db.update("TABLE_RUMORS", rumor["id"], {"evidence_expired": True})
            return


def _draft_follow_up(rumor_id):
    """Reopened: ask pipeline.verify for a fresh clarification draft."""
    import app  # lazy to avoid circular import at module load time
    _, outbound = app._verify_rumor(rumor_id)
    return outbound["id"] if outbound else None
