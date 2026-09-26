"""Wire-level protocol helpers: CRC, register maps, framing."""

from aurora_sensor_agent.protocol.crc import CrcError, crc8, verify_word

__all__ = ["CrcError", "crc8", "verify_word"]
