"""CRC-8 as used by the Sensirion SHT4x sensor.

The SHT4x sends each 16-bit measurement word as two bytes followed by a CRC-8 checksum.
The checksum protects against corrupted I²C reads: if a bit flips on the wire, the CRC will
not match and the reading must be rejected, not trusted.

Parameters (from the SHT4x datasheet):
- polynomial: 0x31 (x^8 + x^5 + x^4 + 1)
- initialisation: 0xFF
- reflect in/out: no
- final XOR: none

Think of the CRC like a checksum digit on a barcode: cheap to compute, and it turns a silent
data corruption into a loud, catchable error.
"""

from __future__ import annotations

_POLYNOMIAL = 0x31
_INIT = 0xFF
_MASK = 0xFF


class CrcError(ValueError):
    """Raised when a received CRC byte does not match the computed checksum."""


def crc8(data: bytes) -> int:
    """Compute the SHT4x CRC-8 over ``data`` and return a byte (0-255)."""
    crc = _INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            high_bit_set = crc & 0x80
            crc = (crc << 1) & _MASK
            if high_bit_set:
                crc ^= _POLYNOMIAL
    return crc


def verify_word(msb: int, lsb: int, checksum: int) -> int:
    """Verify a 16-bit sensor word against its CRC byte and return the raw value.

    Raises ``CrcError`` if the checksum does not match. On success returns the 16-bit raw
    value ``(msb << 8) | lsb``, ready for conversion to temperature or humidity.
    """
    for name, value in (("msb", msb), ("lsb", lsb), ("checksum", checksum)):
        if not 0 <= value <= 0xFF:
            raise ValueError(f"{name} must be a byte (0-255), got {value}")

    expected = crc8(bytes((msb, lsb)))
    if expected != checksum:
        raise CrcError(f"CRC mismatch: computed 0x{expected:02X}, received 0x{checksum:02X}")
    return (msb << 8) | lsb
