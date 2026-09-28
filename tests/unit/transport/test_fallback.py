"""Unit tests for the MQTT-primary / HTTP-fallback transport."""

from __future__ import annotations

import pytest

from aurora_sensor_agent.transport.fallback import FallbackTransport
from aurora_sensor_agent.transport.memory import InMemoryTransport


class _CloseSpy(InMemoryTransport):
    def __init__(self, *, failing: bool = False) -> None:
        super().__init__(failing=failing)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_uses_primary_when_it_succeeds() -> None:
    primary = InMemoryTransport()
    fallback = InMemoryTransport()
    transport = FallbackTransport(primary, fallback)

    transport.publish("topic", b"payload")

    assert primary.delivered == 1
    assert fallback.delivered == 0
    assert transport.primary_failures == 0


def test_falls_back_to_http_when_primary_fails() -> None:
    primary = InMemoryTransport(failing=True)
    fallback = InMemoryTransport()
    transport = FallbackTransport(primary, fallback)

    transport.publish("topic", b"payload")

    assert fallback.delivered == 1
    assert transport.primary_failures == 1
    assert transport.fallback_deliveries == 1


def test_propagates_when_both_fail() -> None:
    primary = InMemoryTransport(failing=True)
    fallback = InMemoryTransport(failing=True)
    transport = FallbackTransport(primary, fallback)

    with pytest.raises(ConnectionError):
        transport.publish("topic", b"payload")

    assert transport.primary_failures == 1
    assert transport.fallback_deliveries == 0


def test_close_closes_both() -> None:
    primary = _CloseSpy()
    fallback = _CloseSpy()
    transport = FallbackTransport(primary, fallback)

    transport.close()

    assert primary.closed is True
    assert fallback.closed is True
