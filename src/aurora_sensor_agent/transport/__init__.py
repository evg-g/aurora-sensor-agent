"""Uplink transports (the ``Transport`` seam).

Milestone 9 ships only an in-memory transport, used by the run loop and the soak test so the whole
agent can be exercised with no network. The real MQTT (primary) and HTTP (fallback) transports land
in milestones 10-11.
"""
