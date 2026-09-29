"""A physics-flavoured model of a medical fridge, deterministic in time.

This is not a rigorous thermodynamic model — it is a *believable* one, good enough to exercise the
excursion logic downstream. It has the four features that matter for testing:

- a **setpoint** the fridge holds (≈4 °C for vaccines),
- **door-open events** that briefly warm it toward room temperature and then recover,
- **sensor noise** (small random jitter on each sample),
- a slow **drift** (a gentle sine, standing in for the compressor duty cycle).

Determinism is the whole point. ``sample(t)`` depends only on ``t`` and the seed, never on call
order or how many times it has been called, so replaying the same timestamps reproduces the same
readings exactly. The randomness is derived from an integer mix of the seed and the millisecond
timestamp — never from hashing a string — so it is stable across processes regardless of
``PYTHONHASHSEED``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

_SECONDS_PER_HOUR = 3600.0
_DEFAULT_HORIZON_S = 7 * 24 * _SECONDS_PER_HOUR  # a week of door events, pre-scheduled


def _mixed_rng(seed: int, stream: int, t_seconds: float) -> random.Random:
    """A ``Random`` seeded deterministically from (seed, stream, quantised time).

    ``stream`` separates independent noise channels (temperature vs humidity) so they do not
    correlate. Time is quantised to the millisecond so tiny float differences do not change the
    draw. No string hashing, so the result is identical across processes and runs.
    """
    millis = round(t_seconds * 1000.0)
    mixed = (seed & 0xFFFFFFFF) * 0x9E3779B1
    mixed ^= (stream & 0xFFFF) * 0x85EBCA77
    mixed ^= millis & 0xFFFFFFFFFFFF
    return random.Random(mixed)


@dataclass
class ThermalModel:
    """A deterministic temperature + humidity source for one fridge."""

    seed: int = 0
    setpoint_c: float = 4.0
    ambient_c: float = 22.0
    noise_std_c: float = 0.05
    drift_amplitude_c: float = 0.3
    drift_period_s: float = _SECONDS_PER_HOUR
    baseline_humidity_pct: float = 45.0
    humidity_noise_pct: float = 0.4
    humidity_coupling: float = 1.5  # %RH gained per °C above setpoint
    mean_door_interval_s: float = 1800.0
    door_intensity: float = 0.45  # fraction of (ambient-setpoint) a long opening reaches
    door_tau_open_s: float = 90.0
    door_tau_recover_s: float = 300.0
    horizon_s: float = _DEFAULT_HORIZON_S
    _doors: list[tuple[float, float]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._doors = self._schedule_doors()

    def _schedule_doors(self) -> list[tuple[float, float]]:
        """Pre-schedule (start, duration) door openings across the horizon, seeded."""
        rng = random.Random((self.seed & 0xFFFFFFFF) ^ 0xD00D)
        events: list[tuple[float, float]] = []
        t = 0.0
        while True:
            t += rng.expovariate(1.0 / self.mean_door_interval_s)
            if t >= self.horizon_s:
                break
            duration = rng.uniform(20.0, 120.0)
            events.append((t, duration))
        return events

    def _drift(self, t_seconds: float) -> float:
        return self.drift_amplitude_c * math.sin(2.0 * math.pi * t_seconds / self.drift_period_s)

    def _door_effect(self, t_seconds: float) -> float:
        """Sum the warming contribution of every door event at time ``t``."""
        peak_gain = (self.ambient_c - self.setpoint_c) * self.door_intensity
        total = 0.0
        for start, duration in self._doors:
            if t_seconds < start:
                continue
            end = start + duration
            if t_seconds < end:
                # Door open: warm up toward the peak.
                total += peak_gain * (1.0 - math.exp(-(t_seconds - start) / self.door_tau_open_s))
            else:
                # Door closed again: decay from the peak reached at close.
                peak_at_close = peak_gain * (1.0 - math.exp(-duration / self.door_tau_open_s))
                total += peak_at_close * math.exp(-(t_seconds - end) / self.door_tau_recover_s)
        return total

    def sample(self, t_seconds: float) -> tuple[float, float]:
        """Return ``(temperature_c, humidity_pct)`` at ``t_seconds`` since the model's t=0."""
        temp = (
            self.setpoint_c
            + self._drift(t_seconds)
            + self._door_effect(t_seconds)
            + _mixed_rng(self.seed, 1, t_seconds).gauss(0.0, self.noise_std_c)
        )
        humidity = (
            self.baseline_humidity_pct
            + self.humidity_coupling * (temp - self.setpoint_c)
            + _mixed_rng(self.seed, 2, t_seconds).gauss(0.0, self.humidity_noise_pct)
        )
        humidity = min(100.0, max(0.0, humidity))
        return temp, humidity


__all__ = ["ThermalModel"]
