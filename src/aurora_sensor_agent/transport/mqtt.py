"""The real MQTT uplink to the broker — the primary telemetry path.

A batch payload is published to the device's telemetry topic with **QoS 1** (at least once). That
pairs with the batch's device-generated idempotency key: the broker may redeliver a message after a
reconnect, but the server drops a duplicate batch, so "at least once" on the wire becomes "exactly
once" in the database.

``paho-mqtt`` runs its own network loop on a background thread and auto-reconnects. ``publish``
waits for the broker to acknowledge the message (PUBACK) so a delivery failure surfaces
*synchronously* — that is what lets the agent's drain loop catch it, leave the readings buffered,
and retry with backoff (see ``agent.SensorAgent._drain``).

The paho client is created through an injected ``client_factory`` so the unit tests can drive the
transport with a fake client and no broker at all; the SIL tier (``tests/sil/``) exercises the real
client against a Mosquitto container.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from typing import Protocol, cast

_log = logging.getLogger("aurora_sensor_agent.transport.mqtt")


class MqttError(ConnectionError):
    """A publish could not be confirmed by the broker; the caller should retry.

    Subclasses ``ConnectionError`` so the agent's drain loop (which catches ``OSError`` and
    ``ConnectionError``) treats it as a transient uplink failure and keeps the readings buffered.
    """


class _MessageInfo(Protocol):
    """The part of paho's ``MQTTMessageInfo`` this transport uses."""

    rc: int

    def wait_for_publish(self, timeout: float | None = ...) -> None: ...

    def is_published(self) -> bool: ...


class _MqttClient(Protocol):
    """The subset of ``paho.mqtt.client.Client`` this transport depends on.

    Declaring it as a Protocol keeps the transport testable: a fake client in the unit tests only
    has to provide these members, and the real paho client satisfies them structurally.
    """

    on_connect: Callable[..., None] | None
    on_disconnect: Callable[..., None] | None

    def username_pw_set(self, username: str | None, password: str | None = ...) -> None: ...

    def connect(self, host: str, port: int = ..., keepalive: int = ...) -> int: ...

    def disconnect(self) -> int: ...

    def loop_start(self) -> int | None: ...

    def loop_stop(self) -> int | None: ...

    def publish(self, topic: str, payload: bytes | str, qos: int = ...) -> _MessageInfo: ...


def _default_client_factory(client_id: str) -> _MqttClient:
    """Build a real paho v2 client. Imported lazily so the module loads without paho at rest."""
    from paho.mqtt.client import Client
    from paho.mqtt.enums import CallbackAPIVersion

    return cast("_MqttClient", Client(CallbackAPIVersion.VERSION2, client_id=client_id or None))


class MqttTransport:
    """A ``Transport`` that publishes batches to an MQTT broker with QoS 1.

    Connection is lazy: the first ``publish`` (or an explicit ``connect``) opens the socket and
    starts the network loop. If the broker is unreachable, or the message is not acknowledged within
    ``publish_timeout``, a :class:`MqttError` is raised so the agent retries later.
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        *,
        username: str | None = None,
        password: str | None = None,
        client_id: str = "",
        keepalive: int = 60,
        qos: int = 1,
        connect_timeout: float = 10.0,
        publish_timeout: float = 10.0,
        client_factory: Callable[[str], _MqttClient] | None = None,
    ) -> None:
        if qos not in (0, 1, 2):
            raise ValueError(f"qos must be 0, 1, or 2, got {qos}")
        self._host = host
        self._port = port
        self._keepalive = keepalive
        self._qos = qos
        self._connect_timeout = connect_timeout
        self._publish_timeout = publish_timeout
        factory = client_factory if client_factory is not None else _default_client_factory
        self._client = factory(client_id)
        if username is not None:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = threading.Event()
        self._started = False

    def _on_connect(self, *args: object) -> None:
        # paho v2 signature: (client, userdata, connect_flags, reason_code, properties). A reason
        # code that is truthy/non-zero means failure; treat anything else as connected.
        reason = args[3] if len(args) >= 4 else None
        if _reason_is_success(reason):
            self._connected.set()
        else:
            self._connected.clear()
            _log.warning("mqtt connect refused", extra={"reason": str(reason)})

    def _on_disconnect(self, *args: object) -> None:
        self._connected.clear()

    def connect(self) -> None:
        """Open the connection and start the network loop. Raises :class:`MqttError` on failure."""
        if self._connected.is_set():
            return
        try:
            self._client.connect(self._host, self._port, self._keepalive)
            if not self._started:
                self._client.loop_start()
                self._started = True
        except OSError as exc:  # DNS failure, refused connection, etc.
            raise MqttError(f"cannot reach broker at {self._host}:{self._port}: {exc}") from exc
        if not self._connected.wait(self._connect_timeout):
            raise MqttError(
                f"broker at {self._host}:{self._port} did not confirm the connection "
                f"within {self._connect_timeout}s"
            )

    def publish(self, topic: str, payload: bytes) -> None:
        """Publish ``payload`` to ``topic`` and wait for the broker to acknowledge it."""
        if not self._connected.is_set():
            self.connect()
        try:
            info = self._client.publish(topic, payload, self._qos)
            info.wait_for_publish(self._publish_timeout)
        except (OSError, RuntimeError, ValueError) as exc:
            # paho raises RuntimeError/ValueError when the queue is full or the client is not
            # connected, and OSError on a socket error. All are "retry later" for us.
            raise MqttError(f"publish to {topic} failed: {exc}") from exc
        if not info.is_published() or info.rc != 0:
            raise MqttError(f"publish to {topic} was not acknowledged (rc={info.rc})")

    def close(self) -> None:
        """Stop the network loop and disconnect. Safe to call more than once."""
        if self._started:
            self._client.loop_stop()
            self._started = False
        with contextlib.suppress(OSError):
            self._client.disconnect()
        self._connected.clear()


def _reason_is_success(reason: object) -> bool:
    """paho v2 passes a ReasonCode (``.is_failure``) on connect; older shims pass an int rc."""
    is_failure = getattr(reason, "is_failure", None)
    if isinstance(is_failure, bool):
        return not is_failure
    if isinstance(reason, int):
        return reason == 0
    # None or an unexpected type: assume success (the wait/PUBACK path still guards delivery).
    return True


__all__ = ["MqttError", "MqttTransport"]
