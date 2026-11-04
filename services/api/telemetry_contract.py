"""Validation against the canonical JSON Schema for telemetry events."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, FormatChecker


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "docs" / "telemetry" / "event-schemas.json"


@lru_cache(maxsize=1)
def _validator() -> Draft7Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, format_checker=FormatChecker())


def validate_telemetry_contract(event: dict[str, Any]) -> None:
    """Raise a sanitized ValueError unless the complete event matches the contract."""
    errors = sorted(_validator().iter_errors(event), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "event"
        raise ValueError(f"Telemetry contract violation at {path}")
