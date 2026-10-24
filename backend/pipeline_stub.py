"""Canned pipeline outputs so P1 routes work before P2 ships the real Bedrock
pipeline. Shapes match plan.md §3.4. Swap the import in app.py to pipeline
(P2's module) when ready.
"""


def extract(text: str, clusters: list, entity_ids: list) -> dict:
    """Step 1: extract & cluster. Returns v3 §4 Step 1 shape."""
    text_lower = text.lower()
    if "shelter a" in text_lower and ("clos" in text_lower or "shut" in text_lower):
        return {
            "question_type": "rumor",
            "claims": [{"text": "Shelter A is closed", "entity_ids": ["SH-A"]}],
            "cluster_match": _match_cluster(clusters, "shelter a") or "R-002",
            "new_cluster_claim": None,
        }
    return {
        "question_type": "other",
        "claims": [{"text": text[:120], "entity_ids": []}],
        "cluster_match": None,
        "new_cluster_claim": text[:80],
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
        "reply_text": "Shelter A is OPEN as of 04:10 (City EOC). Reply MORE for details.",
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
