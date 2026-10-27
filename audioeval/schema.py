"""Required output contract (brief section 2) and validation."""

from __future__ import annotations

import json
from typing import Any

EMOTIONAL_TONES = ("neutral", "satisfied", "frustrated", "upset", "distressed")
INTENSITIES = ("low", "medium", "high")
NOISE_SEVERITIES = ("none", "low", "medium", "high")
AUDIO_QUALITIES = ("clear", "slightly_impaired", "severely_impaired")

FIELDS = (
    "emotional_tone",
    "emotional_intensity",
    "background_noise_present",
    "background_noise_type",
    "background_noise_severity",
    "audio_quality",
    "speaker_overlap_present",
    "long_silence_present",
    "confidence",
)

ENUM_FIELDS = {
    "emotional_tone": EMOTIONAL_TONES,
    "emotional_intensity": INTENSITIES,
    "background_noise_severity": NOISE_SEVERITIES,
    "audio_quality": AUDIO_QUALITIES,
}
BOOL_FIELDS = ("background_noise_present", "speaker_overlap_present", "long_silence_present")


class SchemaError(ValueError):
    pass


def validate_prediction(obj: Any) -> dict:
    """Return the object with fields in canonical order, or raise SchemaError."""
    if not isinstance(obj, dict):
        raise SchemaError("prediction must be a JSON object")
    missing = [f for f in FIELDS if f not in obj]
    extra = [k for k in obj if k not in FIELDS]
    if missing:
        raise SchemaError(f"missing fields: {', '.join(missing)}")
    if extra:
        raise SchemaError(f"unexpected fields: {', '.join(extra)}")
    for field, allowed in ENUM_FIELDS.items():
        if obj[field] not in allowed:
            raise SchemaError(f"{field}={obj[field]!r} not in {allowed}")
    for field in BOOL_FIELDS:
        if not isinstance(obj[field], bool):
            raise SchemaError(f"{field} must be a boolean")
    if not isinstance(obj["background_noise_type"], str):
        raise SchemaError("background_noise_type must be a string")
    conf = obj["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        raise SchemaError("confidence must be a number in [0.0, 1.0]")
    if not obj["background_noise_present"]:
        if obj["background_noise_type"] != "" or obj["background_noise_severity"] != "none":
            raise SchemaError("no noise requires empty type and severity 'none'")
    elif obj["background_noise_severity"] == "none":
        raise SchemaError("noise present requires severity other than 'none'")
    return {f: obj[f] for f in FIELDS}


def parse_label(text: str) -> dict:
    """Parse a manifest result_json cell. Labels are validated loosely (types and enums only)."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"result_json is not valid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise SchemaError("result_json must be a JSON object")
    for field, allowed in ENUM_FIELDS.items():
        if field in obj and obj[field] not in allowed:
            raise SchemaError(f"label {field}={obj[field]!r} not in {allowed}")
    return obj


def to_json(pred: dict) -> str:
    return json.dumps({f: pred[f] for f in FIELDS}, ensure_ascii=False)
