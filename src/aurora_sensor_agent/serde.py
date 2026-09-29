"""Serialise a ``Reading`` to and from the JSON line stored in the buffer and sent uplink.

One place owns the wire shape of a reading, so the buffer, the batch envelope, and (later) the MQTT
transport all agree. The format is a compact JSON object; ``measured_at`` is an ISO-8601 UTC string.
Round-tripping is exact for the raw 16-bit words, and close-enough for the floats (they are derived
from the raw words anyway, so a consumer can always recompute them).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from aurora_sensor_agent.models import Reading

_SCHEMA_VERSION = 1


def reading_to_json(reading: Reading) -> str:
    """Serialise one ``Reading`` to a single-line JSON string."""
    return json.dumps(
        {
            "v": _SCHEMA_VERSION,
            "measured_at": reading.measured_at.astimezone(UTC).isoformat(),
            "temperature_c": reading.temperature_c,
            "humidity_pct": reading.humidity_pct,
            "raw_temperature": reading.raw_temperature,
            "raw_humidity": reading.raw_humidity,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def reading_from_json(payload: str) -> Reading:
    """Parse a JSON string produced by :func:`reading_to_json` back into a ``Reading``."""
    data = json.loads(payload)
    measured_at = datetime.fromisoformat(data["measured_at"])
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=UTC)
    return Reading(
        temperature_c=float(data["temperature_c"]),
        humidity_pct=float(data["humidity_pct"]),
        measured_at=measured_at,
        raw_temperature=int(data["raw_temperature"]),
        raw_humidity=int(data["raw_humidity"]),
    )


__all__ = ["reading_from_json", "reading_to_json"]
