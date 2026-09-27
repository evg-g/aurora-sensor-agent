"""Command-line entry point for the sensor agent.

Milestone 8 adds the ``sim`` subcommand: it runs the real SHT4x driver against the simulated chip
and prints readings, so you can watch the sample → validate → convert path work end to end with no
hardware. The full run loop (buffer → publish) is wired up in later milestones.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from aurora_sensor_agent import __version__
from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aurora-agent",
        description="Aurora Clinic cold-chain sensor agent.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    sim = subparsers.add_parser("sim", help="Run the driver against the simulated sensor.")
    sim.add_argument("--count", type=int, default=5, help="Number of readings to take (default 5).")
    sim.add_argument(
        "--interval", type=float, default=1.0, help="Seconds between readings (default 1.0)."
    )
    sim.add_argument("--seed", type=int, default=0, help="Thermal model seed (default 0).")
    return parser


def _run_sim(count: int, interval: float, seed: int) -> int:
    clock = SystemClock()
    driver = Sht4xDriver(SimulatedSht4xBus(clock, ThermalModel(seed=seed)), clock)
    for index in range(count):
        reading = driver.measure(Precision.HIGH)
        print(
            f"{reading.measured_at.isoformat()}  "
            f"T={reading.temperature_c:6.2f} C  "
            f"RH={reading.humidity_pct:5.1f} %"
        )
        if index < count - 1:
            clock.sleep(interval)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sim":
        return _run_sim(count=args.count, interval=args.interval, seed=args.seed)

    # No subcommand: print usage so the CLI is never a silent no-op.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
