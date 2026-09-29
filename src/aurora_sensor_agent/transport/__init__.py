"""Uplink transports (the ``Transport`` seam).

- ``memory`` — an in-memory fake used by the run loop, soak, and fleet tests so the whole agent can
  be exercised with no network (milestone 9).
- ``mqtt`` — the real MQTT primary path over paho-mqtt, QoS 1 (milestone 11).
- ``http`` — the HTTP fallback to the API's batch endpoint (milestone 11).
- ``fallback`` — MQTT primary with the HTTP fallback wired together (milestone 11).

All satisfy the ``Transport`` protocol in ``protocols.py`` (``publish``/``close``).
"""

from aurora_sensor_agent.transport.fallback import FallbackTransport
from aurora_sensor_agent.transport.http import HttpTransport, HttpTransportError
from aurora_sensor_agent.transport.memory import InMemoryTransport, TransportUnavailableError
from aurora_sensor_agent.transport.mqtt import MqttError, MqttTransport

__all__ = [
    "FallbackTransport",
    "HttpTransport",
    "HttpTransportError",
    "InMemoryTransport",
    "MqttError",
    "MqttTransport",
    "TransportUnavailableError",
]
