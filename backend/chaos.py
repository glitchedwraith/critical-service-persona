"""Chaos endpoints that mutate state to drive the demo (plan.md §5 phase 5)."""

# TODO(P1 phase 5):
# def city_site_down(): system.city_site_online = False
# def rumor_wave(): inject 12 "Shelter A closed" messages from seed/scripts/rumors.json
# def shelter_a_full(): authority-2 report, SH-A.status=full, mark SH-A clarifications outdated
# def conflicting_report(): inject authority-4 resident "Shelter D closed"
# def advance_clock(minutes: int): clock.advance(minutes); trigger rumor_loop tick
# def expire_bulletin(bulletin_id: str): set expires_at < sim_clock
