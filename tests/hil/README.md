# `tests/hil/` — hardware-in-the-loop (real Pi + SHT4x)

These run the driver against a **real** SHT4x over a real I²C bus. They are marked `@pytest.mark.hil`
and are **deselected by default** everywhere else in this repo, so nothing here ever runs on a laptop
or in the normal CI matrix.

They only run when both are true:

- the test is selected with `-m hil` (the nightly `hil` job does this), and
- hardware is present — `tests/hil/conftest.py` skips them unless `/dev/i2c-1` exists or
  `AURORA_HIL=1` is set, so even a bare `pytest` (no `-m`) stays green with no hardware.

## Wiring (Raspberry Pi + SHT4x)

| SHT4x pin | Pi pin |
|---|---|
| VDD | 3V3 (pin 1) |
| GND | GND (pin 6) |
| SDA | GPIO2 / SDA1 (pin 3) |
| SCL | GPIO3 / SCL1 (pin 5) |

Enable I²C (`sudo raspi-config` → Interface Options → I²C), confirm the chip at `0x44`
(`i2cdetect -y 1`), install `smbus2`, then run `AURORA_HIL=1 pytest tests/hil -m hil`. The nightly
`hil` CI job runs on a self-hosted runner labelled `aurora-hil` and is gated behind the
`HIL_ENABLED` repo variable.
