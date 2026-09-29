"""An in-memory ``Transport`` for tests and the offline run loop.

It keeps every published payload in a list, and can be flipped to "failing" so the agent's retry,
backoff, and store-and-forward paths can be exercised with no broker. This is not a mock — it is a
working fake transport whose only difference from the real one is that "the network" is a list.
"""

from __future__ import annotations


class TransportUnavailableError(ConnectionError):
    """Raised by a failing :class:`InMemoryTransport` to imitate an unreachable broker."""


class InMemoryTransport:
    """A ``Transport`` that records published messages, or fails on demand."""

    def __init__(self, *, failing: bool = False, retain: bool = True) -> None:
        self._failing = failing
        self._retain = retain
        self.published: list[tuple[str, bytes]] = []
        self.publish_attempts = 0
        self.delivered = 0

    def set_failing(self, failing: bool) -> None:
        """Turn the simulated outage on or off."""
        self._failing = failing

    def publish(self, topic: str, payload: bytes) -> None:
        self.publish_attempts += 1
        if self._failing:
            raise TransportUnavailableError("broker unreachable")
        self.delivered += 1
        if self._retain:
            # A soak run sets retain=False so the transport itself does not grow without bound.
            self.published.append((topic, payload))

    def close(self) -> None:
        # Nothing to tear down; kept for protocol conformance.
        return None


__all__ = ["InMemoryTransport", "TransportUnavailableError"]
