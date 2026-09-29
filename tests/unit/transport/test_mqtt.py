"""Unit tests for the MQTT transport, driven by a fake paho client (no broker)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from aurora_sensor_agent.transport.mqtt import MqttError, MqttTransport


class _FakeReason:
    """Stands in for paho's ReasonCode: the transport only reads ``is_failure``."""

    def __init__(self, *, is_failure: bool) -> None:
        self.is_failure = is_failure


class _FakeMessageInfo:
    def __init__(self, *, published: bool = True, rc: int = 0) -> None:
        self._published = published
        self.rc = rc
        self.waited = False

    def wait_for_publish(self, timeout: float | None = None) -> None:
        self.waited = True

    def is_published(self) -> bool:
        return self._published


class _FakeMqttClient:
    """A minimal stand-in for ``paho.mqtt.client.Client``."""

    def __init__(
        self,
        *,
        connect_ok: bool = True,
        connect_raises: bool = False,
        publish_raises: bool = False,
        info: _FakeMessageInfo | None = None,
    ) -> None:
        self.on_connect: Callable[..., None] | None = None
        self.on_disconnect: Callable[..., None] | None = None
        self._connect_ok = connect_ok
        self._connect_raises = connect_raises
        self._publish_raises = publish_raises
        self._info = info if info is not None else _FakeMessageInfo()
        self.published: list[tuple[str, bytes | str, int]] = []
        self.loop_running = False
        self.disconnected = False
        self.credentials: tuple[str, str | None] | None = None

    def username_pw_set(self, username: str | None, password: str | None = None) -> None:
        self.credentials = (username or "", password)

    def connect(self, host: str, port: int = 1883, keepalive: int = 60) -> int:
        if self._connect_raises:
            raise OSError("connection refused")
        if self.on_connect is not None:
            self.on_connect(self, None, {}, _FakeReason(is_failure=not self._connect_ok), None)
        return 0

    def disconnect(self) -> int:
        self.disconnected = True
        return 0

    def loop_start(self) -> None:
        self.loop_running = True

    def loop_stop(self) -> None:
        self.loop_running = False

    def publish(self, topic: str, payload: bytes | str, qos: int = 0) -> _FakeMessageInfo:
        if self._publish_raises:
            raise OSError("socket error")
        self.published.append((topic, payload, qos))
        return self._info


def _transport(
    client: _FakeMqttClient,
    *,
    qos: int = 1,
    username: str | None = None,
    password: str | None = None,
) -> MqttTransport:
    return MqttTransport(
        "broker.local",
        1883,
        qos=qos,
        username=username,
        password=password,
        connect_timeout=0.2,
        publish_timeout=0.2,
        client_factory=lambda _client_id: client,
    )


def test_publish_sends_payload_with_configured_qos() -> None:
    # Arrange
    client = _FakeMqttClient()
    transport = _transport(client, qos=1)

    # Act
    transport.publish("aurora/v1/clinic/c/device/d/telemetry", b'{"v":1}')

    # Assert
    assert client.published == [("aurora/v1/clinic/c/device/d/telemetry", b'{"v":1}', 1)]
    assert client.loop_running is True


def test_connect_socket_error_raises_mqtt_error() -> None:
    client = _FakeMqttClient(connect_raises=True)
    transport = _transport(client)

    with pytest.raises(MqttError, match="cannot reach broker"):
        transport.publish("topic", b"x")


def test_broker_refusing_connection_times_out() -> None:
    client = _FakeMqttClient(connect_ok=False)
    transport = _transport(client)

    with pytest.raises(MqttError, match="did not confirm the connection"):
        transport.publish("topic", b"x")


def test_unacknowledged_publish_raises() -> None:
    client = _FakeMqttClient(info=_FakeMessageInfo(published=False))
    transport = _transport(client)

    with pytest.raises(MqttError, match="not acknowledged"):
        transport.publish("topic", b"x")


def test_nonzero_return_code_raises() -> None:
    client = _FakeMqttClient(info=_FakeMessageInfo(published=True, rc=4))
    transport = _transport(client)

    with pytest.raises(MqttError, match="not acknowledged"):
        transport.publish("topic", b"x")


def test_publish_socket_error_raises() -> None:
    client = _FakeMqttClient(publish_raises=True)
    transport = _transport(client)

    with pytest.raises(MqttError, match="publish to topic failed"):
        transport.publish("topic", b"x")


def test_close_stops_loop_and_disconnects() -> None:
    client = _FakeMqttClient()
    transport = _transport(client)
    transport.publish("topic", b"x")

    transport.close()

    assert client.loop_running is False
    assert client.disconnected is True
    transport.close()  # idempotent, no error


def test_invalid_qos_rejected() -> None:
    with pytest.raises(ValueError, match="qos must be"):
        _transport(_FakeMqttClient(), qos=3)


def test_credentials_set_when_provided() -> None:
    client = _FakeMqttClient()
    _transport(client, username="dev", password="secret")

    assert client.credentials == ("dev", "secret")
