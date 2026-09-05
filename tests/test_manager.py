from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.ai.errors import (
    AIConfigurationError,
    ImageResolutionError,
    ProviderRequestError,
)
from custom_components.plant_care.ai.manager import PlantAnalysisManager
from custom_components.plant_care.ai.models import PlantAnalysis, PlantAnalysisContext
from custom_components.plant_care.const import (
    AI_PROVIDER_OPENAI,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DOMAIN,
    OPT_AI_API_KEY,
    OPT_AI_ENABLED,
    OPT_AI_MODEL,
    OPT_AI_PROVIDER,
)
from custom_components.plant_care.image import ResolvedPlantImage


def result() -> PlantAnalysis:
    return PlantAnalysis.from_ai_dict(
        {
            "health_score": 88,
            "status": "healthy",
            "attention_required": False,
            "confidence": 0.91,
            "primary_issue": None,
            "summary": "No visible signs of acute stress.",
            "observations": ["Even leaf color"],
            "recommended_actions": ["Continue current watering schedule"],
            "urgency": "low",
            "watering": {"recommendation": "monitor", "reason": "Stable moisture"},
        },
        analyzed_at=datetime(2026, 9, 5, 12, tzinfo=UTC),
    )


def entry_with_options(hass, **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "peace_lily", CONF_PLANT_NAME: "Peace Lily"},
        options=options,
        unique_id="peace_lily",
    )
    entry.add_to_hass(hass)
    return entry


class ImageResolver:
    async def async_resolve(self, **kwargs):
        return ResolvedPlantImage(b"\xff\xd8\xffimage", "image/jpeg")


class MissingImageResolver:
    async def async_resolve(self, **kwargs):
        raise ImageResolutionError("No image is configured")


class ContextBuilder:
    async def async_build(self):
        return PlantAnalysisContext({}, {}, {}, {})


class Provider:
    def __init__(self, provider_result=None, error=None):
        self.provider_result = provider_result
        self.error = error
        self.context = None

    async def async_analyze(self, image, image_mime_type, plant_context):
        self.context = plant_context
        if self.error:
            raise self.error
        return self.provider_result


def manager(hass, entry, provider, image_resolver=None):
    coordinator = SimpleNamespace(async_refresh=AsyncMock(), data={})
    storage = SimpleNamespace(async_store_analysis=AsyncMock())
    instance = PlantAnalysisManager(
        hass,
        entry,
        coordinator,
        storage,
        context_builder=ContextBuilder(),
        image_resolver=image_resolver or ImageResolver(),
        provider_factory=lambda: provider,
    )
    return instance, coordinator, storage


async def test_ai_disabled(hass):
    entry = entry_with_options(hass, **{OPT_AI_ENABLED: False})
    instance, _, _ = manager(hass, entry, Provider(result()))
    with pytest.raises(AIConfigurationError, match="disabled"):
        await instance.async_analyze()


async def test_missing_api_key(hass):
    entry = entry_with_options(
        hass,
        **{
            OPT_AI_ENABLED: True,
            OPT_AI_PROVIDER: AI_PROVIDER_OPENAI,
            OPT_AI_MODEL: "gpt-4o-mini",
            OPT_AI_API_KEY: "",
        },
    )
    instance = PlantAnalysisManager(
        hass,
        entry,
        SimpleNamespace(data={}),
        SimpleNamespace(),
    )
    with pytest.raises(AIConfigurationError, match="API key"):
        await instance.async_analyze()


async def test_invalid_provider(hass):
    entry = entry_with_options(
        hass,
        **{
            OPT_AI_ENABLED: True,
            OPT_AI_PROVIDER: "gemini",
            OPT_AI_API_KEY: "unused",
        },
    )
    instance = PlantAnalysisManager(
        hass,
        entry,
        SimpleNamespace(data={}),
        SimpleNamespace(),
    )
    with pytest.raises(AIConfigurationError, match="Unsupported AI provider"):
        await instance.async_analyze()


async def test_missing_image(hass):
    entry = entry_with_options(hass, **{OPT_AI_ENABLED: True})
    instance, _, _ = manager(hass, entry, Provider(result()), MissingImageResolver())
    with pytest.raises(ImageResolutionError, match="No image"):
        await instance.async_analyze()


async def test_provider_failure_is_not_stored(hass):
    entry = entry_with_options(hass, **{OPT_AI_ENABLED: True})
    provider = Provider(error=ProviderRequestError("network failed"))
    instance, coordinator, storage = manager(hass, entry, provider)
    with pytest.raises(ProviderRequestError):
        await instance.async_analyze()
    storage.async_store_analysis.assert_not_awaited()
    coordinator.async_refresh.assert_not_awaited()


async def test_manager_success_persists_and_refreshes_one_plant(hass):
    entry = entry_with_options(hass, **{OPT_AI_ENABLED: True})
    provider = Provider(result())
    instance, coordinator, storage = manager(hass, entry, provider)

    returned = await instance.async_analyze(image_entity_id="camera.plant")

    assert returned.health_score == 88
    storage.async_store_analysis.assert_awaited_once_with("peace_lily", returned)
    coordinator.async_refresh.assert_awaited_once()
    assert provider.context is not None
