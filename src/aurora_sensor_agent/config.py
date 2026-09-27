"""Agent configuration, validated at startup.

One frozen ``AgentConfig`` object is built once and passed down. Validation happens here (pydantic),
so a bad threshold or a zero interval fails loudly at start instead of misbehaving at 3 a.m. in a
clinic. Milestone 9 adds the behaviour knobs: calibration, the median filter window, the excursion
threshold policy, the store-and-forward buffer, batching, and backoff.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ThresholdPolicy(BaseModel):
    """The temperature band a fridge must stay inside, and the excursion timing rules.

    A vaccine fridge is typically held at 2-8 °C. ``dwell_minutes`` is how long the temperature may
    sit outside the band before it counts as a real excursion (so a door opening does not alarm).
    ``recovery_minutes`` is how long it must be back inside the band before the excursion clears.
    """

    min_temperature_c: float = 2.0
    max_temperature_c: float = 8.0
    dwell_minutes: float = Field(default=15.0, gt=0)
    recovery_minutes: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _check_band(self) -> ThresholdPolicy:
        if self.max_temperature_c <= self.min_temperature_c:
            raise ValueError(
                "max_temperature_c must be greater than min_temperature_c "
                f"(got min={self.min_temperature_c}, max={self.max_temperature_c})"
            )
        return self


class BackoffConfig(BaseModel):
    """Exponential-backoff-with-jitter settings for retrying a failed publish.

    Delay for attempt *n* (0-based) is ``base_seconds * factor**n``, capped at ``max_seconds``, then
    (if ``jitter``) drawn uniformly in ``[0, that]`` — "full jitter", which spreads a reconnecting
    fleet out instead of letting every device retry in lockstep.
    """

    base_seconds: float = Field(default=1.0, gt=0)
    factor: float = Field(default=2.0, ge=1.0)
    max_seconds: float = Field(default=60.0, gt=0)
    jitter: bool = True

    @model_validator(mode="after")
    def _check_cap(self) -> BackoffConfig:
        if self.max_seconds < self.base_seconds:
            raise ValueError("max_seconds must be >= base_seconds")
        return self


class AgentConfig(BaseModel):
    """Static configuration for a single device agent."""

    device_id: str = Field(min_length=1)
    clinic_id: str = Field(min_length=1)
    sample_interval_seconds: float = Field(default=30.0, gt=0)

    # Signal conditioning.
    calibration_offset_c: float = 0.0
    median_window: int = Field(default=5, ge=1)

    # Excursion detection.
    thresholds: ThresholdPolicy = ThresholdPolicy()

    # Store-and-forward buffer.
    buffer_path: str = ":memory:"
    buffer_capacity: int = Field(default=10_000, gt=0)

    # Uplink batching + retry.
    batch_max_readings: int = Field(default=100, gt=0)
    backoff: BackoffConfig = BackoffConfig()

    # Local clock-step detection (wall clock vs monotonic divergence per cycle).
    max_clock_skew_seconds: float = Field(default=60.0, gt=0)

    # Reported in the health beacon.
    firmware_version: str = "0.1.0"


__all__ = ["AgentConfig", "BackoffConfig", "ThresholdPolicy"]
