"""Error-path tests for the replay bus. The happy path is covered by the driver-contract suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_sensor_agent.replay.i2c import (
    ReplayExhaustedError,
    ReplayFrame,
    ReplayI2CBus,
)
from aurora_sensor_agent.sim.i2c import encode_word


def _one_frame_bus() -> ReplayI2CBus:
    response = encode_word(25000) + encode_word(30000)
    return ReplayI2CBus([ReplayFrame(command=0xFD, response=response)])


def test_replays_recorded_response() -> None:
    bus = _one_frame_bus()
    bus.write(0x44, b"\xfd")
    assert len(bus.read(0x44, 6)) == 6


def test_command_drift_is_detected() -> None:
    bus = _one_frame_bus()
    bus.write(0x44, b"\xe0")  # driver sent a different command than was recorded
    with pytest.raises(OSError, match="trace drift"):
        bus.read(0x44, 6)


def test_reading_past_the_end_raises() -> None:
    bus = _one_frame_bus()
    bus.write(0x44, b"\xfd")
    bus.read(0x44, 6)
    with pytest.raises(ReplayExhaustedError):
        bus.read(0x44, 6)


def test_multibyte_write_is_rejected() -> None:
    bus = _one_frame_bus()
    with pytest.raises(OSError, match="single-byte"):
        bus.write(0x44, b"\xfd\x00")


def test_close_is_a_noop() -> None:
    _one_frame_bus().close()  # must not raise


def test_from_jsonl_round_trips(tmp_path: Path) -> None:
    response = (encode_word(1000) + encode_word(2000)).hex()
    trace = tmp_path / "trace.jsonl"
    trace.write_text(f'{{"command": "0xFD", "response": "{response}"}}\n', encoding="utf-8")

    bus = ReplayI2CBus.from_jsonl(trace)
    bus.write(0x44, b"\xfd")
    assert bus.read(0x44, 6).hex() == response


def test_from_jsonl_rejects_malformed_record(tmp_path: Path) -> None:
    trace = tmp_path / "bad.jsonl"
    trace.write_text('{"command": "0xFD"}\n', encoding="utf-8")  # no response field

    with pytest.raises(ValueError, match="malformed trace record"):
        ReplayI2CBus.from_jsonl(trace)


def test_from_jsonl_rejects_empty_file(tmp_path: Path) -> None:
    trace = tmp_path / "empty.jsonl"
    trace.write_text("\n  \n", encoding="utf-8")

    with pytest.raises(ValueError, match="no frames"):
        ReplayI2CBus.from_jsonl(trace)
