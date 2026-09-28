"""The device must emit payloads its own telemetry contract accepts, and the schema must be strict.

The batch envelope is built by the agent's real ``serde`` + ``build_batches`` code, then validated
against the committed ``contracts/telemetry.schema.json``. If the device wire format and the schema
ever drift apart, this fails — which is the point, since the API validates inbound messages against
a vendored copy of the same schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from aurora_sensor_agent.logic.batch import build_batches
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.serde import reading_to_json

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "contracts"
_SCHEMA_PATH = _CONTRACTS / "telemetry.schema.json"
_ASYNCAPI_PATH = _CONTRACTS / "telemetry.asyncapi.yaml"

# The versions the server (milestone 10) accepts. A device on any of these can be deployed against a
# server on the current version — the N-1 rule. Kept here so a device-side change that outruns the
# server's support window fails a test.
SERVER_SUPPORTED_VERSIONS = {1, 2}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _reading(temp: float = 4.5, seq_seed: int = 0) -> Reading:
    return Reading(
        temperature_c=temp,
        humidity_pct=45.0,
        measured_at=datetime(2026, 9, 28, 12, 0, seq_seed, tzinfo=UTC),
        raw_temperature=25000 + seq_seed,
        raw_humidity=30000 + seq_seed,
    )


def _real_envelope() -> dict[str, Any]:
    rows = [(i, reading_to_json(_reading(seq_seed=i))) for i in range(3)]
    batch = build_batches(rows, device_id="11111111-1111-1111-1111-111111111111", max_readings=100)[
        0
    ]
    parsed: dict[str, Any] = json.loads(batch.payload)
    return parsed


def test_real_device_batch_conforms_to_schema(validator: Draft202012Validator) -> None:
    # Arrange + Act: build exactly what the agent would publish.
    envelope = _real_envelope()

    # Assert: it validates, with the fields the schema requires.
    validator.validate(envelope)
    assert envelope["v"] in SERVER_SUPPORTED_VERSIONS
    assert envelope["device_id"] == "11111111-1111-1111-1111-111111111111"
    assert envelope["idempotency_key"]
    assert len(envelope["readings"]) == 3
    assert envelope["readings"][0]["reading"]["v"] in SERVER_SUPPORTED_VERSIONS


def test_device_version_is_within_the_servers_support_window() -> None:
    # The device emits v1 readings (no battery sensor); a v2 server must still accept them (N-1).
    envelope = _real_envelope()
    assert envelope["readings"][0]["reading"]["v"] in SERVER_SUPPORTED_VERSIONS


def test_schema_accepts_a_v2_reading_with_battery(validator: Draft202012Validator) -> None:
    envelope = {
        "v": 2,
        "device_id": "d",
        "idempotency_key": "k",
        "readings": [
            {
                "sequence": 0,
                "reading": {
                    "v": 2,
                    "measured_at": "2026-09-28T12:00:00+00:00",
                    "temperature_c": 4.5,
                    "humidity_pct": 40.0,
                    "battery_pct": 88.0,
                },
            }
        ],
    }
    validator.validate(envelope)


def test_schema_rejects_missing_idempotency_key(validator: Draft202012Validator) -> None:
    envelope = _real_envelope()
    del envelope["idempotency_key"]
    with pytest.raises(ValidationError):
        validator.validate(envelope)


def test_schema_rejects_unknown_top_level_field(validator: Draft202012Validator) -> None:
    envelope = _real_envelope()
    envelope["surprise"] = True
    with pytest.raises(ValidationError):
        validator.validate(envelope)


def test_schema_rejects_out_of_range_humidity(validator: Draft202012Validator) -> None:
    envelope = _real_envelope()
    envelope["readings"][0]["reading"]["humidity_pct"] = 150.0
    with pytest.raises(ValidationError):
        validator.validate(envelope)


def test_schema_rejects_empty_reading_batch(validator: Draft202012Validator) -> None:
    envelope = _real_envelope()
    envelope["readings"] = []
    with pytest.raises(ValidationError):
        validator.validate(envelope)


def test_asyncapi_document_describes_the_telemetry_topic() -> None:
    doc = yaml.safe_load(_ASYNCAPI_PATH.read_text(encoding="utf-8"))
    assert doc["asyncapi"].startswith("3.")
    text = _ASYNCAPI_PATH.read_text(encoding="utf-8")
    assert "aurora/v1/clinic/" in text
    assert "device/" in text and "telemetry" in text
