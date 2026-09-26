"""Unit tests for agent configuration validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aurora_sensor_agent.config import AgentConfig


def test_valid_config_is_accepted() -> None:
    config = AgentConfig(device_id="dev-1", clinic_id="clinic-1", sample_interval_seconds=15)

    assert config.device_id == "dev-1"
    assert config.sample_interval_seconds == 15


def test_default_sample_interval() -> None:
    config = AgentConfig(device_id="dev-1", clinic_id="clinic-1")

    assert config.sample_interval_seconds == 30.0


@pytest.mark.parametrize("interval", [0, -5])
def test_non_positive_interval_is_rejected(interval: float) -> None:
    with pytest.raises(ValidationError):
        AgentConfig(device_id="dev-1", clinic_id="clinic-1", sample_interval_seconds=interval)


def test_empty_device_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(device_id="", clinic_id="clinic-1")
