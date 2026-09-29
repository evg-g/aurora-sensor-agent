"""The HTTP fallback uplink — used when the MQTT broker is unreachable.

The device posts the *same* batch payload it would publish over MQTT to the API's batch endpoint,
``POST /api/v1/devices/{device_id}/telemetry:batch``, authenticating with the per-device secret in
the ``X-Device-Secret`` header (unlike MQTT, HTTP carries a header per request, so the device proves
its identity directly instead of relying on a broker ACL).

Delivery failures — a network error, a 5xx, or a 429 — raise :class:`HttpTransportError` so the
agent leaves the readings buffered and retries with backoff. A 4xx that is not 429 means the request
itself is wrong (bad credentials, a contract violation); it is still raised so nothing is silently
dropped, but it is logged at error level because retrying will not fix it on its own. Payloads are
contract-validated before they ever reach here, so a 4xx in practice means a credential problem.
"""

from __future__ import annotations

import logging

import httpx

_log = logging.getLogger("aurora_sensor_agent.transport.http")


class HttpTransportError(ConnectionError):
    """An HTTP batch upload failed; the caller should retry (subclass of ``ConnectionError``)."""


class HttpTransport:
    """A ``Transport`` that uploads batches over HTTP to the API's telemetry batch endpoint.

    ``topic`` is ignored (it is an MQTT concept); the endpoint is fixed by ``device_id``. The httpx
    client can be injected for tests; otherwise one is created and owned by the transport.
    """

    def __init__(
        self,
        base_url: str,
        device_id: str,
        secret: str,
        *,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._device_id = device_id
        self._secret = secret
        self._url = f"{self._base_url}/api/v1/devices/{device_id}/telemetry:batch"
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def publish(self, topic: str, payload: bytes) -> None:
        """Upload ``payload`` (a serialised batch envelope) to the batch endpoint."""
        headers = {
            "X-Device-Secret": self._secret,
            "Content-Type": "application/json",
        }
        try:
            response = self._client.post(self._url, content=payload, headers=headers)
        except httpx.RequestError as exc:  # DNS, connect, read timeout, etc.
            raise HttpTransportError(f"POST {self._url} failed: {exc}") from exc

        if response.is_success:
            return
        if response.status_code >= 500 or response.status_code == 429:
            raise HttpTransportError(
                f"POST {self._url} returned {response.status_code} (server/rate-limit; will retry)"
            )
        _log.error(
            "telemetry upload rejected",
            extra={"status": response.status_code, "device_id": self._device_id},
        )
        raise HttpTransportError(
            f"POST {self._url} returned {response.status_code} "
            f"(client error; check device credentials/contract)"
        )

    def close(self) -> None:
        """Close the httpx client if this transport created it."""
        if self._owns_client:
            self._client.close()


__all__ = ["HttpTransport", "HttpTransportError"]
