"""Replay implementations: feed recorded traces back through the same seams.

A replay bus returns bytes captured earlier from the simulator (or, one day, from real hardware),
so a specific sequence of readings can be reproduced byte-for-byte. That turns a one-off bug into a
permanent regression fixture.
"""
