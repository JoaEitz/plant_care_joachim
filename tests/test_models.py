from datetime import UTC, datetime

import pytest

from custom_components.plant_care.ai.errors import InvalidAnalysisError
from custom_components.plant_care.ai.models import PlantAnalysis
from custom_components.plant_care.ai.openai import parse_openai_response


def valid_payload(**changes):
    payload = {
        "health_score": 72,
        "status": "stressed",
        "attention_required": True,
        "confidence": 0.84,
        "primary_issue": "Possible overwatering",
        "summary": "Leaves are drooping while soil remains moist.",
        "observations": ["Leaf droop", "Leaves remain green"],
        "recommended_actions": ["Wait before watering", "Check drainage"],
        "urgency": "medium",
        "watering": {
            "recommendation": "wait",
            "reason": "Measured soil moisture remains high",
        },
    }
    payload.update(changes)
    return payload


def test_structured_response_parsing():
    result = PlantAnalysis.from_ai_dict(
        valid_payload(),
        analyzed_at=datetime(2026, 9, 5, 12, tzinfo=UTC),
    )

    assert result.health_score == 72
    assert result.status == "stressed"
    assert result.watering is not None
    assert result.watering.recommendation == "wait"
    assert PlantAnalysis.from_dict(result.to_dict()) == result


@pytest.mark.parametrize(
    "changes",
    [
        {"health_score": 101},
        {"health_score": 50.5},
        {"confidence": 2},
        {"status": "perfect"},
        {"attention_required": "yes"},
        {"observations": "drooping"},
        {"untrusted_extra": "value"},
        {"watering": {"recommendation": "guess", "reason": "unknown"}},
    ],
)
def test_invalid_ai_response(changes):
    with pytest.raises(InvalidAnalysisError):
        PlantAnalysis.from_ai_dict(
            valid_payload(**changes),
            analyzed_at=datetime.now(UTC),
        )


def test_openai_output_extraction():
    import json

    result = parse_openai_response(
        {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(valid_payload())}
                    ],
                }
            ]
        }
    )
    assert result.health_score == 72


def test_openai_malformed_response():
    with pytest.raises(InvalidAnalysisError, match="malformed JSON"):
        parse_openai_response({"output_text": "not-json"})
