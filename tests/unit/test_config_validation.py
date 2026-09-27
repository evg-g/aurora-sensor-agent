"""Validation tests for the config models added in milestone 9."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aurora_sensor_agent.config import AgentConfig, BackoffConfig, ThresholdPolicy


def test_threshold_band_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="greater than min_temperature_c"):
        ThresholdPolicy(min_temperature_c=8.0, max_temperature_c=2.0)


def test_dwell_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ThresholdPolicy(dwell_minutes=0.0)


def test_backoff_cap_must_be_at_least_base() -> None:
    with pytest.raises(ValidationError, match="max_seconds must be"):
        BackoffConfig(base_seconds=10.0, max_seconds=1.0)


def test_defaults_build_a_valid_agent_config() -> None:
    config = AgentConfig(device_id="d", clinic_id="c")
    assert config.thresholds.min_temperature_c == 2.0
    assert config.thresholds.max_temperature_c == 8.0
    assert config.backoff.factor == 2.0


def test_zero_interval_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(device_id="d", clinic_id="c", sample_interval_seconds=0.0)
