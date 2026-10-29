import copy

import pytest

from audioeval.schema import SchemaError, parse_label, validate_prediction
from conftest import LABEL


def test_valid_prediction_roundtrip():
    assert validate_prediction(dict(LABEL)) == LABEL


@pytest.mark.parametrize(
    "field,value",
    [
        ("emotional_tone", "angry"),
        ("emotional_intensity", "extreme"),
        ("audio_quality", "ok"),
        ("background_noise_present", "false"),
        ("confidence", 1.2),
        ("confidence", True),
        ("background_noise_type", None),
    ],
)
def test_invalid_values_rejected(field, value):
    pred = dict(LABEL)
    pred[field] = value
    with pytest.raises(SchemaError):
        validate_prediction(pred)


def test_missing_and_extra_fields():
    pred = dict(LABEL)
    del pred["confidence"]
    with pytest.raises(SchemaError, match="missing"):
        validate_prediction(pred)
    with pytest.raises(SchemaError, match="unexpected"):
        validate_prediction(LABEL | {"name": "x.wav"})


def test_noise_invariants():
    bad = copy.deepcopy(LABEL) | {"background_noise_type": "tv"}
    with pytest.raises(SchemaError):
        validate_prediction(bad)
    bad = LABEL | {"background_noise_present": True, "background_noise_type": "tv", "background_noise_severity": "none"}
    with pytest.raises(SchemaError):
        validate_prediction(bad)


def test_parse_label():
    assert parse_label('{"emotional_tone": "upset"}')["emotional_tone"] == "upset"
    with pytest.raises(SchemaError):
        parse_label("{not json")
    with pytest.raises(SchemaError):
        parse_label('{"emotional_tone": "furious"}')
