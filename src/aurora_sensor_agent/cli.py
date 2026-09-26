"""Command-line entry point for the sensor agent.

For milestone 1 this only reports the version. The run loop (sample → validate → evaluate →
buffer → publish) is wired up in later milestones.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from aurora_sensor_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aurora-agent",
        description="Aurora Clinic cold-chain sensor agent.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run. Returns a process exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    # No subcommand yet: print usage so the CLI is never a silent no-op.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
