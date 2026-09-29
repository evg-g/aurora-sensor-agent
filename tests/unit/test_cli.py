"""Unit tests for the CLI entry point. No I/O beyond captured stdout."""

from __future__ import annotations

import pytest

from aurora_sensor_agent import __version__
from aurora_sensor_agent.cli import main


def test_main_with_no_args_prints_help_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "aurora-agent" in captured.out


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse's --version action raises SystemExit(0) after printing.
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_sim_subcommand_prints_readings(capsys: pytest.CaptureFixture[str]) -> None:
    # interval 0 keeps the real clock's sleep instant, so the test stays fast.
    exit_code = main(["sim", "--count", "2", "--interval", "0", "--seed", "1"])

    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert exit_code == 0
    assert len(lines) == 2
    assert all("T=" in line and "RH=" in line for line in lines)


def test_run_subcommand_prints_beacon(capsys: pytest.CaptureFixture[str]) -> None:
    # interval 0 keeps the real-clock sleeps instant; the loop's timed behaviour (excursions) is
    # proven deterministically against a FakeClock in tests/unit/test_agent.py.
    exit_code = main(["run", "--count", "3", "--interval", "0", "--seed", "1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "cycles=3" in captured.out
    assert "readings_ok=3" in captured.out
    assert "excursion=normal" in captured.out
