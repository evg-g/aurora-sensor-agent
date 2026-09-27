"""Tests for the deterministic fridge thermal model."""

from __future__ import annotations

from aurora_sensor_agent.sim.thermal import ThermalModel


def test_same_seed_and_time_give_identical_samples() -> None:
    a = ThermalModel(seed=1)
    b = ThermalModel(seed=1)

    for t in (0.0, 30.0, 123.456, 3600.0):
        assert a.sample(t) == b.sample(t)


def test_sampling_is_independent_of_call_order() -> None:
    # Property that makes replay possible: sample(t) depends only on t, not on history.
    model = ThermalModel(seed=2)
    forward = [model.sample(t) for t in (0.0, 10.0, 20.0, 30.0)]
    backward = [model.sample(t) for t in (30.0, 20.0, 10.0, 0.0)][::-1]

    assert forward == backward


def test_different_seeds_diverge() -> None:
    a = ThermalModel(seed=1)
    b = ThermalModel(seed=999)

    samples_a = [a.sample(t) for t in range(0, 3600, 60)]
    samples_b = [b.sample(t) for t in range(0, 3600, 60)]

    assert samples_a != samples_b


def test_readings_stay_in_a_physical_band_over_a_day() -> None:
    model = ThermalModel(seed=3)

    for t in range(0, 24 * 3600, 60):
        temperature, humidity = model.sample(float(t))
        assert -5.0 < temperature < 25.0
        assert 0.0 <= humidity <= 100.0


def test_door_events_actually_warm_the_fridge() -> None:
    # Over a day there must be at least one opening that pushes clearly above the setpoint.
    model = ThermalModel(seed=4, setpoint_c=4.0)

    peak = max(model.sample(float(t))[0] for t in range(0, 24 * 3600, 30))

    assert peak > model.setpoint_c + 2.0
