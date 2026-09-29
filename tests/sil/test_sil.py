"""Software-in-the-loop: the agent's real transports against the real API + broker in Docker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aurora_sensor_agent.agent import assemble_agent
from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.config import AgentConfig
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.logic.batch import build_batches
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.serde import reading_to_json
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel
from aurora_sensor_agent.transport.http import HttpTransport
from aurora_sensor_agent.transport.mqtt import MqttTransport
from tests.sil.conftest import ProvisionedDevice, SilStack, poll_timeseries_points

pytestmark = pytest.mark.sil


def _reading(index: int) -> Reading:
    return Reading(
        temperature_c=4.5 + 0.1 * index,
        humidity_pct=45.0,
        measured_at=datetime.now(UTC) - timedelta(seconds=30 - index),
        raw_temperature=25000 + index,
        raw_humidity=30000 + index,
    )


def test_http_batch_is_ingested_end_to_end(
    sil_stack: SilStack, provisioned_device: ProvisionedDevice
) -> None:
    # Arrange: a real batch envelope built by the agent's own code.
    rows = [(i, reading_to_json(_reading(i))) for i in range(3)]
    batch = build_batches(rows, device_id=provisioned_device.device_id, max_readings=100)[0]
    transport = HttpTransport(
        sil_stack.api_url, provisioned_device.device_id, provisioned_device.secret
    )

    # Act: publish over the real HTTP fallback path.
    try:
        transport.publish("unused-topic", batch.payload)
    finally:
        transport.close()

    # Assert: the API stored the readings.
    total = poll_timeseries_points(
        sil_stack.api_url, sil_stack.admin_token, provisioned_device.device_id
    )
    assert total >= 3


def test_agent_over_mqtt_is_ingested_end_to_end(
    sil_stack: SilStack, provisioned_device: ProvisionedDevice
) -> None:
    # Arrange: the whole agent, simulated sensor, real MQTT transport to the broker.
    clock = SystemClock()
    config = AgentConfig(
        device_id=provisioned_device.device_id,
        clinic_id=provisioned_device.clinic_id,
        sample_interval_seconds=0.01,  # tiny: five cycles finish fast on the real clock
    )
    driver = Sht4xDriver(SimulatedSht4xBus(clock, ThermalModel(seed=1)), clock)
    transport = MqttTransport(
        sil_stack.mqtt_host,
        sil_stack.mqtt_port,
        client_id=f"sil-{provisioned_device.device_id}",
    )
    agent = assemble_agent(
        config,
        sample=lambda: driver.measure(Precision.HIGH),
        clock=clock,
        transport=transport,
    )

    # Act: five sample -> publish cycles over MQTT.
    try:
        agent.run(5)
    finally:
        transport.close()

    # Assert: the MQTT worker ingested what the agent published.
    total = poll_timeseries_points(
        sil_stack.api_url, sil_stack.admin_token, provisioned_device.device_id, timeout=45.0
    )
    assert total >= 1
    assert agent.beacon().published_readings == 5
