# tests/unit/gpio — the status LED and buzzer

Tests for driving GPIO with no hardware. `gpiozero` ships a `MockFactory` that emulates pins in
memory; pointing `Device.pin_factory` at it lets `src/aurora_sensor_agent/real/gpio.py` — which
really calls `gpiozero.OutputDevice` — run on a laptop and in CI.

What they prove:

- `make_output_pin` drives a pin high and low, and `is_active` reads it back.
- The `StatusIndicator` lights green/amber/red and the buzzer correctly for each state, over the real
  `gpiozero` code path.
- The state really reaches the underlying mock pin (not just our wrapper's boolean).

The pure state→colour mapping is tested separately over fake pins in `tests/unit/logic/test_indicator.py`;
this tier is specifically about the `gpiozero` seam.
