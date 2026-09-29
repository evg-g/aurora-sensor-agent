"""Capture a deterministic SHT4x trace from the simulator into a replay fixture.

Run from the repo root:

    # WSL (Ubuntu-24.04)
    uv run python scripts/record_trace.py

It drives the simulated chip with a manual (deterministic) clock and writes each command/response
exchange to ``tests/fixtures/traces/sim_baseline.jsonl``. The replay bus and the driver-contract
suite read that file back, so the recorded readings are reproduced byte-for-byte on any machine.

Re-run this only when you deliberately want to regenerate the fixture (e.g. the sim model changed);
the committed file is the source of truth for the replay tests.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aurora_sensor_agent.drivers.sht4x import DEFAULT_ADDRESS, Precision
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel

SEED = 42
SAMPLE_COUNT = 60
INTERVAL_S = 30.0
OUTPUT = Path("tests/fixtures/traces/sim_baseline.jsonl")


class _ManualClock:
    """A tiny deterministic clock, inlined so this script depends only on the package."""

    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=UTC)
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)


def main() -> int:
    clock = _ManualClock()
    bus = SimulatedSht4xBus(clock, ThermalModel(seed=SEED))
    command = Precision.HIGH.command

    records: list[str] = []
    for _ in range(SAMPLE_COUNT):
        bus.write(DEFAULT_ADDRESS, bytes((command,)))
        clock.sleep(Precision.HIGH.delay_s)
        response = bus.read(DEFAULT_ADDRESS, 6)
        records.append(json.dumps({"command": f"0x{command:02X}", "response": response.hex()}))
        clock.sleep(INTERVAL_S)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(records) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} frames to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
