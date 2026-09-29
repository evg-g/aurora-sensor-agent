"""Skip the hil tier unless real hardware is present, even when it is selected.

The ``hil`` marker keeps these out of the normal ``-m "not hil"`` runs. This guard is the second
belt: it skips them when no I²C bus is present, so a bare ``pytest`` (no marker filter) on a laptop
stays green instead of trying to open ``/dev/i2c-1``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _hardware_present() -> bool:
    return os.environ.get("AURORA_HIL") == "1" or Path("/dev/i2c-1").exists()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _hardware_present():
        return
    skip = pytest.mark.skip(reason="hil tier: no hardware (set AURORA_HIL=1 on a wired device)")
    for item in items:
        if "hil" in item.keywords:
            item.add_marker(skip)
