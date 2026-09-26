"""Register-level unit tests for the SHT4x CRC-8.

No hardware, no I/O. The known-answer vector is the one printed in the Sensirion datasheet:
CRC-8 over the bytes 0xBE 0xEF is 0x92.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aurora_sensor_agent.protocol.crc import CrcError, crc8, verify_word


def test_datasheet_known_answer_vector() -> None:
    # Arrange / Act
    result = crc8(bytes((0xBE, 0xEF)))

    # Assert
    assert result == 0x92


def test_verify_word_returns_raw_value_on_match() -> None:
    msb, lsb = 0xBE, 0xEF
    checksum = crc8(bytes((msb, lsb)))

    raw = verify_word(msb, lsb, checksum)

    assert raw == 0xBEEF


def test_verify_word_rejects_corrupted_checksum() -> None:
    msb, lsb = 0xBE, 0xEF
    good = crc8(bytes((msb, lsb)))
    corrupted = good ^ 0x01  # flip one bit

    with pytest.raises(CrcError):
        verify_word(msb, lsb, corrupted)


@pytest.mark.parametrize("bad_value", [-1, 256, 999])
def test_verify_word_rejects_non_byte_inputs(bad_value: int) -> None:
    with pytest.raises(ValueError):
        verify_word(bad_value, 0x00, 0x00)


@given(st.binary(min_size=0, max_size=32))
def test_crc8_is_always_a_byte(data: bytes) -> None:
    # Property: whatever the input, the checksum fits in one byte.
    assert 0 <= crc8(data) <= 0xFF


@given(msb=st.integers(0, 0xFF), lsb=st.integers(0, 0xFF))
def test_verify_word_round_trips_for_any_valid_word(msb: int, lsb: int) -> None:
    # Property: a word checked against its own CRC always yields the original raw value.
    checksum = crc8(bytes((msb, lsb)))
    assert verify_word(msb, lsb, checksum) == (msb << 8) | lsb
