# `tests/unit/transport/` — uplink transport tests (no network)

These prove the real MQTT and HTTP transports behave correctly **without a broker or a server**:

- `test_mqtt.py` drives `MqttTransport` with a fake paho client (injected through `client_factory`).
  It checks the connect handshake, QoS, the "wait for PUBACK" acknowledgement, and that every
  failure mode raises `MqttError` (a `ConnectionError`) so the agent buffers and retries.
- `test_http.py` drives `HttpTransport` with `respx` mocking httpx at the transport layer. It checks
  the batch URL, the `X-Device-Secret` header, and that 5xx / 429 / 4xx / network errors all raise
  `HttpTransportError`.
- `test_fallback.py` proves `FallbackTransport` uses MQTT first and only falls back to HTTP when the
  primary raises, and that it re-raises when both fail.

The real broker/server end-to-end path is the SIL tier (`tests/sil/`), which needs Docker.
