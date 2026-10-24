"""Fallback text templates used by the validator when regeneration still fails.

Per TrueSignal-Plan-v3.md §4 & §5:
- When evidence is expired OR a regen attempt still trips the validator, we
  must fall back to a safe templated line rather than ship an un-grounded draft.
- Every sentence we hand to the officer / resident must carry its source and
  "as of HH:MM".
"""

CANT_CONFIRM = "Last official update {hhmm} — current status can't be confirmed."
HOLDING_REPLY = "We're checking. Last official update: {hhmm} ({source})."
NEEDS_OFFICER = (
    "Conflicting reports as of {hhmm}. Awaiting officer confirmation — "
    "last official update: {hhmm} ({source})."
)


def cant_confirm(sim_clock: str) -> str:
    """v3 §4: 'Last official update HH:MM — current status can't be confirmed.'"""
    return CANT_CONFIRM.format(hhmm=sim_clock or "--:--")


def holding_reply(sim_clock: str, source: str = "City EOC") -> str:
    """v3 §5 'what sends automatically': holding reply when auto-send not OK."""
    return HOLDING_REPLY.format(hhmm=sim_clock or "--:--", source=source)


def needs_officer(sim_clock: str, source: str = "City EOC") -> str:
    """v3 §5: equal-authority conflict path."""
    return NEEDS_OFFICER.format(hhmm=sim_clock or "--:--", source=source)
