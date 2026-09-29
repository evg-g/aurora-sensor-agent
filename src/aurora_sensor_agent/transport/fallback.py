"""MQTT primary with an HTTP fallback — the delivery policy from the spec (§7).

MQTT is the normal path: it is cheap, keeps a session open, and lets the broker fan out to the
backend. When the broker is unreachable (a flaky clinic network, a broker restart), the agent should
not just sit on its buffer if the API's HTTPS endpoint is still reachable — so this transport tries
MQTT first and, only if that raises, falls back to HTTP for that one batch.

Both underlying transports raise ``ConnectionError`` on failure. If MQTT fails, the fallback is
tried; if the fallback also fails, its error propagates so the agent buffers and retries later. The
same batch payload and idempotency key go out on either path, so a batch that "failed" over MQTT but
actually reached the broker, then also went out over HTTP, is de-duplicated by the server.
"""

from __future__ import annotations

import logging

from aurora_sensor_agent.protocols import Transport

_log = logging.getLogger("aurora_sensor_agent.transport.fallback")


class FallbackTransport:
    """Publish over ``primary``; on a ``ConnectionError`` retry the same batch over ``fallback``."""

    def __init__(self, primary: Transport, fallback: Transport) -> None:
        self._primary = primary
        self._fallback = fallback
        self.primary_failures = 0
        self.fallback_deliveries = 0

    def publish(self, topic: str, payload: bytes) -> None:
        try:
            self._primary.publish(topic, payload)
            return
        except (OSError, ConnectionError) as exc:
            self.primary_failures += 1
            _log.warning("primary transport failed; trying fallback", extra={"error": str(exc)})
        # Let a fallback failure propagate: the agent will buffer and retry both paths next cycle.
        self._fallback.publish(topic, payload)
        self.fallback_deliveries += 1

    def close(self) -> None:
        self._primary.close()
        self._fallback.close()


__all__ = ["FallbackTransport"]
