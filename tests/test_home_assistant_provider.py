from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.plant_care.ai.errors import ProviderRateLimitError
from custom_components.plant_care.ai.home_assistant import (
    HomeAssistantAITaskPlantAIProvider,
)
from custom_components.plant_care.ai.models import PlantAnalysisContext
from custom_components.plant_care.image import LOCAL_MEDIA_PREFIX


def ai_task_payload():
    return {
        "health_score": 83,
        "status": "watch",
        "attention_required": True,
        "confidence": 0.87,
        "primary_issue": "Possible dry soil",
        "summary": "Moisture is falling and the leaves show mild droop.",
        "observations": ["Mild leaf droop"],
        "recommended_actions": ["Check soil before watering"],
        "urgency": "medium",
        "watering_recommendation": "check",
        "watering_reason": "The measured moisture trend is falling.",
    }


async def test_home_assistant_ai_task_provider_uses_existing_entity(
    hass, tmp_path: Path
):
    hass.config.media_dirs = {"local": str(tmp_path)}

    async def runner(**kwargs):
        assert kwargs["entity_id"] == "ai_task.google_gemini"
        assert kwargs["structure"] is not None
        attachment = kwargs["attachments"][0]["media_content_id"]
        assert attachment.startswith(LOCAL_MEDIA_PREFIX)
        staged_path = tmp_path / attachment.removeprefix(LOCAL_MEDIA_PREFIX)
        assert staged_path.read_bytes().startswith(b"\xff\xd8\xff")
        assert '"soil_moisture"' in kwargs["instructions"]
        return SimpleNamespace(data=ai_task_payload())

    provider = HomeAssistantAITaskPlantAIProvider(
        hass,
        "ai_task.google_gemini",
        runner=runner,
    )
    context = PlantAnalysisContext(
        plant={"name": "Fern"},
        current={"soil_moisture": {"value": 42}},
        care={},
        history={},
    )

    result = await provider.async_analyze(b"\xff\xd8\xffplant", "image/jpeg", context)

    assert result.health_score == 83
    assert result.watering is not None
    assert result.watering.recommendation == "check"
    assert not list((tmp_path / "plant_care_ai").glob("*"))


async def test_home_assistant_ai_task_provider_maps_quota_error(hass, tmp_path: Path):
    hass.config.media_dirs = {"local": str(tmp_path)}

    async def runner(**kwargs):
        raise HomeAssistantError("RESOURCE_EXHAUSTED: quota exceeded")

    provider = HomeAssistantAITaskPlantAIProvider(hass, None, runner=runner)

    with pytest.raises(ProviderRateLimitError, match="quota"):
        await provider.async_analyze(
            b"\xff\xd8\xffplant",
            "image/jpeg",
            PlantAnalysisContext({}, {}, {}, {}),
        )

    assert not list((tmp_path / "plant_care_ai").glob("*"))
