# tests/unit/protocol

Register- and wire-level tests: command encoding, 16-bit word parsing, **CRC-8 verification
and rejection**, raw→°C/%RH conversion, endianness, out-of-range raw values.

These use a fake I²C bus with a recorded register map (added with the driver in milestone 8)
and `hypothesis` for conversion round-trips. No real hardware.
