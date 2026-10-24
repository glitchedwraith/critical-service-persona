"""Rumor resolution monitor. Runs on inbound and clock-advancing events.

Transitions per plan.md §5 phase 5 and TrueSignal-Plan-v3.md §6.
"""

# TODO(P1 phase 5):
# def tick():
#   for each rumor in monitoring:
#     compare next two 10-sim-min windows vs baseline_rate_per_10min
#     >=50% drop -> status=resolved
#     flat/rising -> status=reopened, call pipeline.verify() for follow-up draft
#     any evidence expired -> evidence_expired=true
