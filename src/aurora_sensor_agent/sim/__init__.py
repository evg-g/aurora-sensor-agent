"""Deterministic simulator of the SHT4x sensor and the fridge it lives in.

The simulator is seeded and pure-in-time: given the same seed and the same timestamp it always
returns the same reading, which is what makes tests reproducible and lets ``replay`` capture a
byte-for-byte trace. It also injects hardware faults on demand (bad CRC, NACK, timeout, …) so the
error paths are testable without breaking a real chip.
"""
