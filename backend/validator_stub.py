"""Pass-through validator until P2 ships backend/validator.py.

Contract (plan.md §3.4):
    validate(draft: dict, ctx: dict) -> tuple[dict, list[str]]
    ctx = {shelters, bulletins, sources, sim_clock}
"""


def validate(draft: dict, ctx: dict):
    """Stub: never modifies the draft, never flags. Swap for the real
    validator by changing `import validator_stub as validator` in app.py."""
    return draft, []
