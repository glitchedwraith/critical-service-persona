"""Validator — the safety core.

Implements every rule in TrueSignal-Plan-v3.md §5. Pure Python, no Bedrock,
no DynamoDB. Called by both pipeline.verify() (which handles regen + fallback)
and app.py (/outbound/{id}/edit).

Contract (plan.md §3.4):
    validate(draft: dict, ctx: dict) -> tuple[dict, list[str]]
    ctx = {shelters, bulletins, sources, sim_clock}

The function MUTATES a copy of the draft to:
- append "as of HH:MM" to factual sentences that lack it (never a reject-cause)
- truncate text over 300 chars and append "... reply MORE"
- downgrade verdicts that fail evidence rules
- force current_status_known=False + templated text when all evidence expired

Returned flags are human-readable strings for the trace / UI. An empty flags
list means "passed". Any flag means "rejected" from the pipeline's point of
view (which should regenerate once, then fall back to templates.py).
"""
import re

from backend import templates


# ---- small helpers ---------------------------------------------------------

_HHMM_RE = re.compile(r"\bas of \d{1,2}:\d{2}\b", re.IGNORECASE)
_SMS_CAP = 300
_TRUNCATE_SUFFIX = "... reply MORE"


def _ts_lt(a, b):
    """Return True iff a < b, treating None as unknown (-> False)."""
    return a is not None and b is not None and a < b


def _not_expired(ts_expires, sim_clock):
    """True if sim_clock < ts_expires (evidence still valid)."""
    if ts_expires is None or sim_clock is None:
        return False
    return sim_clock < ts_expires


def _source_authority(source_id, sources):
    for s in sources or []:
        if s.get("id") == source_id:
            try:
                return int(s.get("authority", 99))
            except (TypeError, ValueError):
                return 99
    return 99  # unknown source => worst authority


def _evidence_live(ev, sources, sim_clock, authority_cap=2):
    """A piece of evidence satisfies 'confirmed/contradicted' if its source has
    authority <= cap AND the evidence is not expired."""
    authority = _source_authority(ev.get("source_id"), sources)
    return authority <= authority_cap and _not_expired(ev.get("expires_at"), sim_clock)


def _shelter_by_id(sid, shelters):
    for s in shelters or []:
        if s.get("id") == sid:
            return s
    return None


# ---- sentence-level helpers ------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _append_as_of(text, hhmm):
    """Ensure every factual sentence contains 'as of HH:MM'. Append once to
    the first sentence lacking it (we don't try to be clever — the sentences
    all describe the same evidence window)."""
    if not text or not hhmm:
        return text
    if _HHMM_RE.search(text):
        return text
    # Insert before a terminal punctuation if present, otherwise append.
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".!?":
        return stripped[:-1] + f" as of {hhmm}" + stripped[-1]
    return (stripped + f" as of {hhmm}.") if stripped else text


def _enforce_cap(text):
    """Truncate to 300 chars + 'reply MORE' tail. v3 §5."""
    if not text or len(text) <= _SMS_CAP:
        return text, False
    head_len = _SMS_CAP - len(_TRUNCATE_SUFFIX) - 1
    head = text[:max(head_len, 0)].rstrip()
    return f"{head} {_TRUNCATE_SUFFIX}", True


# ---- main entry ------------------------------------------------------------

def validate(draft, ctx):
    """Enforce v3 §5 on a Step 2 output.

    Args:
        draft: dict with any subset of {reply_text, clarification_text, text,
            verdict, current_status_known, evidence}. We tolerate the shape used
            by both pipeline.verify() (full Step 2 object) and app.py /edit
            (an outbound row with just "text").
        ctx: {"shelters": [...], "bulletins": [...], "sources": [...],
            "sim_clock": "HH:MM"}

    Returns:
        (fixed_draft, flags). flags is empty on pass.
    """
    fixed = dict(draft)
    flags = []

    shelters = ctx.get("shelters") or []
    bulletins = ctx.get("bulletins") or []
    sources = ctx.get("sources") or []
    sim_clock = ctx.get("sim_clock")

    known_shelter_ids = {s.get("id") for s in shelters if s.get("id")}
    known_addresses = {
        (s.get("address") or "").strip().lower()
        for s in shelters if s.get("address")
    }

    evidence = list(fixed.get("evidence") or [])
    verdict = fixed.get("verdict")

    # Collect text surfaces we'll check / rewrite.
    text_keys = [k for k in ("reply_text", "clarification_text", "text") if k in fixed]

    # ------- Rule: entity IDs mentioned in text must exist -------
    for key in text_keys:
        txt = fixed.get(key) or ""
        for m in re.finditer(r"\bSH-[A-Za-z0-9]+\b", txt):
            sid = m.group(0).upper()
            if sid not in known_shelter_ids:
                flags.append(f"unknown_shelter_id:{sid}")

    # Evidence refs must also resolve.
    for ev in evidence:
        ref = ev.get("ref")
        if ref and ref.startswith("SH-") and ref not in known_shelter_ids:
            flags.append(f"unknown_shelter_id:{ref}")

    # ------- Rule: addresses in text must match the shelters table exactly -------
    # Heuristic: any "123 Something Ave/St/Blvd/Rd/Dr/Way" token.
    addr_pat = re.compile(
        r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9 .'-]*?"
        r"\s+(?:Ave|Avenue|St|Street|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane)\b",
        re.IGNORECASE,
    )
    for key in text_keys:
        txt = fixed.get(key) or ""
        for match in addr_pat.findall(txt):
            if match.strip().lower() not in known_addresses:
                flags.append(f"unknown_address:{match.strip()}")

    # ------- Rule: evidence expiry gates the verdict -------
    live_le2 = [e for e in evidence if _evidence_live(e, sources, sim_clock, 2)]
    all_expired = bool(evidence) and not any(
        _not_expired(e.get("expires_at"), sim_clock) for e in evidence
    )

    if verdict in ("confirmed", "contradicted") and not live_le2:
        # Downgrade — not a hard reject but needs the officer to see it.
        fixed["verdict"] = "unverified"
        flags.append(f"downgraded_{verdict}_no_live_authority")
        verdict = "unverified"

    if all_expired:
        fixed["current_status_known"] = False
        cant = templates.cant_confirm(sim_clock)
        for key in text_keys:
            fixed[key] = cant
        flags.append("all_evidence_expired")

    # ------- Rule: equal-authority conflict -> officer; higher-auth wins otherwise -------
    # We look at live evidence only. Two different source_ids with the same
    # top authority means we can't pick silently.
    if live_le2 and not all_expired:
        top_auth = min(_source_authority(e.get("source_id"), sources) for e in live_le2)
        top = [e for e in live_le2
               if _source_authority(e.get("source_id"), sources) == top_auth]
        distinct_sources = {e.get("source_id") for e in top}
        # If two distinct sources at the same authority appear AND the rumor
        # record (passed in via draft) explicitly marked a conflict, flag it.
        if len(distinct_sources) >= 2 and fixed.get("conflict"):
            flags.append("needs_officer_decision")
            fixed["verdict"] = "unverified"
            for key in text_keys:
                fixed[key] = templates.needs_officer(sim_clock)

    # ------- Rule: factual sentences include "as of HH:MM" -------
    # Append rather than reject (per the task description).
    hhmm_for_append = _best_evidence_hhmm(evidence) or sim_clock
    for key in text_keys:
        txt = fixed.get(key) or ""
        if txt:
            fixed[key] = _append_as_of(txt, hhmm_for_append)

    # ------- Rule: 300 char cap, add "reply MORE" -------
    for key in text_keys:
        txt = fixed.get(key) or ""
        new_txt, truncated = _enforce_cap(txt)
        if truncated:
            fixed[key] = new_txt
            # Not a reject — truncation is a mitigation, matches v3 §5 "Truncate"

    return fixed, flags


def _best_evidence_hhmm(evidence):
    """Prefer last_verified_at, fall back to published_at. Used for 'as of'."""
    for key in ("last_verified_at", "published_at"):
        for ev in evidence or []:
            v = ev.get(key)
            if v:
                return v
    return None
