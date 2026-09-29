"""Unit tests for the HTTP fallback transport, using httpx's MockTransport (no server).

``httpx.MockTransport`` runs a handler in place of the network, so the tests see the exact request
the transport builds (URL, headers, body) and can return any status or raise a network error, with
no dependency on how a URL-pattern library parses the ``:batch`` in the path.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from aurora_sensor_agent.transport.http import HttpTransport, HttpTransportError

BASE = "http://api.local"
DEVICE = "11111111-1111-1111-1111-111111111111"
URL = f"{BASE}/api/v1/devices/{DEVICE}/telemetry:batch"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_successful_upload_posts_payload_with_secret_header() -> None:
    # Arrange
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"accepted": 1})

    transport = HttpTransport(BASE, DEVICE, "s3cr3t", client=_client(handler))

    # Act
    transport.publish("ignored-topic", b'{"v":1,"device_id":"x"}')

    # Assert
    assert len(seen) == 1
    assert seen[0].headers["X-Device-Secret"] == "s3cr3t"
    assert seen[0].headers["Content-Type"] == "application/json"
    assert seen[0].content == b'{"v":1,"device_id":"x"}'
    transport.close()


def test_url_targets_the_device_batch_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    transport = HttpTransport(BASE + "/", DEVICE, "s", client=_client(handler))  # slash trimmed

    transport.publish("topic", b"{}")

    assert str(seen[0].url) == URL
    assert seen[0].method == "POST"


def _status_handler(status: int) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return handler


def test_server_error_raises() -> None:
    transport = HttpTransport(BASE, DEVICE, "s", client=_client(_status_handler(503)))

    with pytest.raises(HttpTransportError, match="503"):
        transport.publish("topic", b"{}")


def test_rate_limited_raises() -> None:
    transport = HttpTransport(BASE, DEVICE, "s", client=_client(_status_handler(429)))

    with pytest.raises(HttpTransportError, match="429"):
        transport.publish("topic", b"{}")


def test_client_error_raises() -> None:
    transport = HttpTransport(BASE, DEVICE, "wrong-secret", client=_client(_status_handler(401)))

    with pytest.raises(HttpTransportError, match="client error"):
        transport.publish("topic", b"{}")


def test_network_error_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    transport = HttpTransport(BASE, DEVICE, "s", client=_client(handler))

    with pytest.raises(HttpTransportError, match="failed"):
        transport.publish("topic", b"{}")


def test_close_closes_owned_client() -> None:
    transport = HttpTransport(BASE, DEVICE, "s")

    transport.close()

    assert transport._client.is_closed is True


def test_injected_client_is_not_closed() -> None:
    client = _client(_status_handler(200))
    transport = HttpTransport(BASE, DEVICE, "s", client=client)

    transport.close()

    assert client.is_closed is False
    client.close()
