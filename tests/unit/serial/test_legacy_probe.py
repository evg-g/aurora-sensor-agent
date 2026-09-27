"""Serial tier: the legacy probe's frame parser (pure) and its I/O over real serial doubles.

The parser tests cover the messy realities of a serial line — split frames, leading garbage, a bad
checksum — with no I/O at all. The I/O tests drive :class:`LegacyProbe` against ``pyserial``'s
``loop://`` (an in-memory loopback) and a ``pty`` pair (a real kernel pseudo-terminal), so the real
``pyserial`` read path runs with no hardware.
"""

from __future__ import annotations

import os
import sys

import pytest

from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.drivers.legacy_probe import (
    FrameParser,
    LegacyProbe,
    ProbeFrameError,
    ProbeReading,
    ProbeTimeoutError,
    checksum,
    encode_frame,
    parse_body,
)
from aurora_sensor_agent.real.serial import open_serial_port

# ---- pure frame parser ---------------------------------------------------------------------


def test_full_frame_in_one_push() -> None:
    parser = FrameParser()
    frames = parser.push(encode_frame(4.12, 45.3))
    assert frames == [b"T=4.12,H=45.3"]
    assert parser.checksum_errors == 0


def test_frame_split_across_two_reads() -> None:
    parser = FrameParser()
    frame = encode_frame(4.0, 45.0)
    assert parser.push(frame[:5]) == []  # partial: nothing yet
    assert parser.push(frame[5:]) == [b"T=4.00,H=45.0"]


def test_leading_garbage_is_discarded() -> None:
    parser = FrameParser()
    frames = parser.push(b"\x00\xffnoise" + encode_frame(3.5, 40.0))
    assert frames == [b"T=3.50,H=40.0"]


def test_two_frames_in_one_push() -> None:
    parser = FrameParser()
    frames = parser.push(encode_frame(1.0, 10.0) + encode_frame(2.0, 20.0))
    assert frames == [b"T=1.00,H=10.0", b"T=2.00,H=20.0"]


def test_bad_checksum_is_dropped_then_resyncs() -> None:
    parser = FrameParser()
    corrupt = bytearray(encode_frame(4.0, 45.0))
    corrupt[2] ^= 0x01  # change a body byte so the checksum no longer matches
    frames = parser.push(bytes(corrupt) + encode_frame(5.0, 50.0))
    assert frames == [b"T=5.00,H=50.0"]  # the good frame still parses
    assert parser.checksum_errors == 1


def test_checksum_is_xor_of_body() -> None:
    assert checksum(b"ABC") == (0x41 ^ 0x42 ^ 0x43)


def test_non_hex_checksum_is_dropped_then_resyncs() -> None:
    parser = FrameParser()
    body = b"T=4.00,H=45.0"
    bad = b"$" + body + b"*ZZ\r\n"  # checksum digits are not hex
    frames = parser.push(bad + encode_frame(6.0, 60.0))
    assert frames == [b"T=6.00,H=60.0"]
    assert parser.checksum_errors == 1


def test_malformed_terminator_resyncs_to_next_frame() -> None:
    parser = FrameParser()
    body = b"T=4.00,H=45.0"
    # Correct checksum but a wrong terminator (';;' instead of CRLF).
    wrong_tail = b"$" + body + b"*" + f"{checksum(body):02X}".encode() + b";;"
    frames = parser.push(wrong_tail + encode_frame(7.0, 70.0))
    assert frames == [b"T=7.00,H=70.0"]
    assert parser.checksum_errors == 1


def test_parse_body_valid() -> None:
    assert parse_body(b"T=4.12,H=45.3") == ProbeReading(temperature_c=4.12, humidity_pct=45.3)


def test_parse_body_missing_field() -> None:
    with pytest.raises(ProbeFrameError, match="missing T or H"):
        parse_body(b"T=4.12")


def test_parse_body_non_numeric() -> None:
    with pytest.raises(ProbeFrameError, match="non-numeric"):
        parse_body(b"T=warm,H=45.3")


# ---- I/O over pyserial loop:// ------------------------------------------------------------


def test_probe_reads_a_frame_over_loopback() -> None:
    port = open_serial_port("loop://", timeout=0.05)
    try:
        port.write(encode_frame(4.12, 45.3))
        probe = LegacyProbe(port, SystemClock())
        reading = probe.read_reading(timeout_s=2.0)
        assert reading.temperature_c == pytest.approx(4.12)
        assert reading.humidity_pct == pytest.approx(45.3)
    finally:
        port.close()


def test_probe_times_out_when_no_frame_arrives() -> None:
    port = open_serial_port("loop://", timeout=0.02)
    try:
        probe = LegacyProbe(port, SystemClock())
        with pytest.raises(ProbeTimeoutError):
            probe.read_reading(timeout_s=0.1)
    finally:
        port.close()


def test_probe_skips_a_corrupt_frame_over_loopback() -> None:
    port = open_serial_port("loop://", timeout=0.05)
    try:
        corrupt = bytearray(encode_frame(4.0, 45.0))
        corrupt[2] ^= 0x01
        port.write(bytes(corrupt) + encode_frame(6.5, 55.0))
        probe = LegacyProbe(port, SystemClock())
        reading = probe.read_reading(timeout_s=2.0)
        assert reading.temperature_c == pytest.approx(6.5)
        assert probe.checksum_errors == 1
    finally:
        port.close()


# ---- I/O over a real pty pair (POSIX only) ------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="pty is POSIX-only")
def test_probe_reads_over_a_pty_pair() -> None:
    import pty

    master, slave = pty.openpty()
    port = open_serial_port(os.ttyname(slave), timeout=0.05)
    try:
        os.write(master, encode_frame(2.5, 30.0))
        probe = LegacyProbe(port, SystemClock())
        reading = probe.read_reading(timeout_s=2.0)
        assert reading.temperature_c == pytest.approx(2.5)
    finally:
        port.close()
        os.close(master)
        os.close(slave)
