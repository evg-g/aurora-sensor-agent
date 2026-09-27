"""Command-line entry point for the sensor agent.

Two subcommands run against the simulator with no hardware:

- ``sim`` (milestone 8) runs the SHT4x driver alone and prints readings, so you can watch the
  sample → validate → convert path.
- ``run`` (milestone 9) runs the whole agent loop — sample → filter → excursion → buffer → publish —
  against the simulated fridge and an in-memory buffer/transport, then prints the health beacon.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from aurora_sensor_agent import __version__
from aurora_sensor_agent.agent import assemble_agent
from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.config import AgentConfig, ThresholdPolicy
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

    run = subparsers.add_parser("run", help="Run the whole agent loop against the simulator.")
    run.add_argument("--count", type=int, default=10, help="Number of cycles to run (default 10).")
    run.add_argument(
        "--interval", type=float, default=0.0, help="Seconds between cycles (default 0.0)."
    )
    run.add_argument("--seed", type=int, default=0, help="Thermal model seed (default 0).")
    run.add_argument(
        "--setpoint",
        type=float,
        default=5.0,
        help="Fridge setpoint °C (default 5.0; try 12 to force an excursion).",
    )
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


def _run_agent(count: int, interval: float, seed: int, setpoint: float) -> int:
    clock = SystemClock()
    config = AgentConfig(
        device_id="sim-fridge",
        clinic_id="sim-clinic",
        thresholds=ThresholdPolicy(dwell_minutes=1.0, recovery_minutes=1.0),
    )
    driver = Sht4xDriver(
        SimulatedSht4xBus(clock, ThermalModel(seed=seed, setpoint_c=setpoint)), clock
    )
    agent = assemble_agent(config, sample=lambda: driver.measure(Precision.HIGH), clock=clock)
    for index in range(count):
        agent.run_cycle()
        if index < count - 1:
            clock.sleep(interval)

    beacon = agent.beacon()
    print(
        f"cycles={beacon.cycles}  readings_ok={beacon.readings_ok}  "
        f"published={beacon.published_readings}  buffer_depth={beacon.buffer_depth}  "
        f"excursion={beacon.excursion_state}  sensor_errors={beacon.sensor_errors}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sim":
        return _run_sim(count=args.count, interval=args.interval, seed=args.seed)

    if args.command == "run":
        return _run_agent(
            count=args.count, interval=args.interval, seed=args.seed, setpoint=args.setpoint
        )

    # No subcommand: print usage so the CLI is never a silent no-op.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
