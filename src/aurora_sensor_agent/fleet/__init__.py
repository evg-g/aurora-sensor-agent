"""The fleet simulator and staged-rollout driver (milestone 11).

A single agent is proven in isolation everywhere else in this repo. The *fleet* pieces here run many
virtual devices at once, which is what a real cold-chain deployment looks like and what the backend
and web repos point their E2E and load tests at:

- ``config`` — the ``fleet.yaml`` schema: devices, their fault profiles, and the rollout cohorts.
- ``simulator`` — ``VirtualDevice`` and ``run_fleet``: N seeded agents against a chosen transport,
  reporting per-device health and an aggregate error rate.
- ``rollout`` — ``StagedRollout``: apply a *verified* OTA update canary → 10% → fleet, measuring the
  error rate after each cohort and halting automatically if it rises past the policy threshold.
"""
