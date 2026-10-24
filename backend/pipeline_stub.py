"""Canned pipeline outputs so P1 routes work before P2 ships the real Bedrock
pipeline. Shapes match plan.md §3.4. Swap the import in app.py to pipeline
(P2's module) when ready.
"""


def extract(text: str, clusters: list, entity_ids: list, entity_labels=None) -> dict:
    """Step 1: extract & cluster. Returns v3 §4 Step 1 shape."""
    tl = text.lower()

    for shelter_phrase, entity_id in (("shelter a", "SH-A"), ("shelter d", "SH-D")):
        if shelter_phrase in tl and ("clos" in tl or "shut" in tl):
            matched = _match_cluster(clusters, shelter_phrase)
            display = shelter_phrase.title()  # "Shelter A" / "Shelter D"
            return {
                "question_type": "rumor",
                "claims": [{"text": f"{display} is closed", "entity_ids": [entity_id]}],
                "cluster_match": matched,
                "new_cluster_claim": None if matched else f"{display} has closed",
            }

    if "water" in tl and any(w in tl for w in ("poison", "contaminat", "unsafe", "bad", "dirty")):
        matched = _match_cluster(clusters, "water")
        return {
            "question_type": "rumor",
            "claims": [{"text": "Tap water is contaminated", "entity_ids": []}],
            "cluster_match": matched,
            "new_cluster_claim": None if matched else "Tap water is contaminated",
        }

    if any(k in tl for k in ("shelter", "water", "open", "safe", "evac")):
        return {
            "question_type": "status_question",
            "claims": [{"text": text[:120], "entity_ids": _mentioned_entities(tl, entity_ids)}],
            "cluster_match": None,
            "new_cluster_claim": None,
        }

    return {
        "question_type": "other",
        "claims": [],
        "cluster_match": None,
        "new_cluster_claim": None,
    }


def verify(rumor: dict, shelters: list, bulletins: list,
           sources: list, sim_clock: str) -> dict:
    """Step 2: verify & draft, pre-validated. Returns v3 §4 Step 2 shape plus
    §3.4 wrapper fields (validator, auto_send_ok)."""
    return {
        "verdict": "contradicted",
        "current_status_known": True,
        "evidence": [{
            "source_id": "SRC-EOC",
            "ref": "SH-A",
            "published_at": "04:10",
            "last_verified_at": "04:10",
            "expires_at": "05:10",
        }],
        "reply_text": f"Shelter A is OPEN as of 04:10 (City EOC). Reply MORE for details.",
        "clarification_text": (
            "UPDATE as of 04:10: Shelter A (Lincoln HS Gym, 123 Example Ave) "
            "is OPEN. Source: City EOC."
        ),
        "validator": {"passed": True, "flags": [], "fallback_used": False},
        "auto_send_ok": True,
    }


def _match_cluster(clusters, needle):
    for c in clusters:
        if needle in (c.get("claim") or "").lower():
            return c.get("id")
    return None


def _mentioned_entities(text_lower, entity_ids):
    found = []
    for eid in entity_ids:
        if eid.lower() in text_lower:
            found.append(eid)
    return found
