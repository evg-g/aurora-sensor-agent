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
