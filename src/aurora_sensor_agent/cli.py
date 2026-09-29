"""Command-line entry point for the sensor agent.

Subcommands, all runnable with no hardware:

- ``sim`` (milestone 8) runs the SHT4x driver alone and prints readings.
- ``run`` (milestone 9) runs the whole agent loop against the simulated fridge and prints the health
  beacon.
- ``fleet`` (milestone 11) runs many virtual devices from a ``fleet.yaml`` and prints their health.
- ``rollout`` (milestone 11) drives a staged OTA rollout (canary → 10% → fleet) across that fleet,
  halting automatically if a cohort's error rate rises.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from aurora_sensor_agent import __version__
from aurora_sensor_agent.agent import assemble_agent
from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.config import AgentConfig, ThresholdPolicy
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.fleet.config import FaultProfile, load_fleet_config
from aurora_sensor_agent.fleet.rollout import StagedRollout
from aurora_sensor_agent.fleet.simulator import run_fleet
from aurora_sensor_agent.ota import OtaVerificationError
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

    fleet = subparsers.add_parser("fleet", help="Run many virtual devices from a fleet.yaml.")
    fleet.add_argument("--config", type=Path, default=Path("fleet.yaml"), help="Fleet config file.")
    fleet.add_argument("--cycles", type=int, default=20, help="Cycles per device (default 20).")

    rollout = subparsers.add_parser("rollout", help="Staged OTA rollout across the fleet.")
    rollout.add_argument("--config", type=Path, default=Path("fleet.yaml"))
    rollout.add_argument("--version", default="1.1.0", help="Version to roll out (default 1.1.0).")
    rollout.add_argument("--cycles", type=int, default=20, help="Cycles per device (default 20).")
    rollout.add_argument(
        "--bad-build",
        action="store_true",
        help="Simulate a bad build (every device's uplink dies after the update) to show the halt.",
    )
    rollout.add_argument("--manifest", type=Path, help="Signed OTA manifest to verify first.")
    rollout.add_argument("--public-key", type=Path, help="Ed25519 public key PEM for verification.")
    rollout.add_argument("--artifact", type=Path, help="Release artifact to integrity-check.")
    rollout.add_argument("--current-version", default="1.0.0", help="Running version (for verify).")
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


def _run_fleet(config_path: Path, cycles: int) -> int:
    config = load_fleet_config(config_path)
    report = run_fleet(config, cycles)
    print(report.summary_table())
    return 0


def _run_rollout(args: argparse.Namespace) -> int:
    config = load_fleet_config(args.config)
    if args.bad_build:
        for spec in config.devices:
            spec.profile_after_update = FaultProfile.DEAD_UPLINK

    rollout = StagedRollout(config, cycles=args.cycles)
    if args.manifest is not None:
        if args.public_key is None or args.artifact is None:
            print("--manifest requires --public-key and --artifact", file=sys.stderr)
            return 2
        try:
            result = rollout.run_verified(
                args.manifest.read_text(encoding="utf-8"),
                args.public_key.read_bytes(),
                args.artifact,
                args.current_version,
            )
        except OtaVerificationError as exc:
            print(f"OTA verification failed, rollout aborted: {exc}", file=sys.stderr)
            return 1
    else:
        result = rollout.run(args.version)

    print(result.summary())
    return 1 if result.halted else 0


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
    if args.command == "fleet":
        return _run_fleet(args.config, args.cycles)
    if args.command == "rollout":
        return _run_rollout(args)

    # No subcommand: print usage so the CLI is never a silent no-op.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
