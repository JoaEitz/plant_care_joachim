from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.ai.services import (
    SERVICE_ANALYZE_PLANT,
    SERVICE_GET_ANALYSIS_HISTORY,
    async_register_ai_services,
)
from custom_components.plant_care.binary_sensor import (
    PlantCareAIAttentionRequiredBinarySensor,
)
from custom_components.plant_care.button import PlantCareAIAnalyzeButton
from custom_components.plant_care.const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DOMAIN,
)
from custom_components.plant_care.sensor import (
    PlantCareAIConfidenceSensor,
    PlantCareAIDiagnosisSensor,
    PlantCareAIHealthScoreSensor,
    PlantCareAILastAnalysisSensor,
    PlantCareAIStatusSensor,
)
from tests.test_manager import result


def make_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "peace_lily", CONF_PLANT_NAME: "Peace Lily"},
        unique_id="peace_lily",
    )
    entry.add_to_hass(hass)
    return entry


async def test_service_action_success(hass):
    entry = make_entry(hass)
    analysis = result()
    analysis_manager = SimpleNamespace(async_analyze=AsyncMock(return_value=analysis))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "analysis_manager": analysis_manager
    }
    async_register_ai_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ANALYZE_PLANT,
        {"config_entry_id": entry.entry_id, "image_entity": "camera.plant"},
        blocking=True,
        return_response=True,
    )

    assert response["health_score"] == 88
    analysis_manager.async_analyze.assert_awaited_once_with(
        image_entity_id="camera.plant",
        media_content_id=None,
        image_path=None,
    )


async def test_service_resolves_existing_plant_device(hass):
    entry = make_entry(hass)
    analysis_manager = SimpleNamespace(async_analyze=AsyncMock(return_value=result()))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "analysis_manager": analysis_manager
    }
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "peace_lily")},
    )
    async_register_ai_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ANALYZE_PLANT,
        {"device_id": [device.id]},
        blocking=True,
        return_response=True,
    )

    assert response["status"] == "healthy"


async def test_history_service_returns_bounded_backend_data(hass):
    entry = make_entry(hass)
    storage = SimpleNamespace(async_get_analyses=AsyncMock(return_value=[result()]))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"storage": storage}
    async_register_ai_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_ANALYSIS_HISTORY,
        {"config_entry_id": entry.entry_id, "limit": 5},
        blocking=True,
        return_response=True,
    )

    assert response["plant_id"] == "peace_lily"
    assert response["analyses"][0]["health_score"] == 88
    storage.async_get_analyses.assert_awaited_once_with("peace_lily", limit=5)


async def test_button_behavior(hass):
    entry = make_entry(hass)
    coordinator = SimpleNamespace(last_update_success=True, data={})
    analysis_manager = SimpleNamespace(async_analyze=AsyncMock())
    button = PlantCareAIAnalyzeButton(entry, coordinator, analysis_manager)

    await button.async_press()

    analysis_manager.async_analyze.assert_awaited_once_with()
    assert button.unique_id == "peace_lily_ai_analyze"


def test_analysis_sensor_states_and_attributes(hass):
    entry = make_entry(hass)
    analysis = result()
    coordinator = SimpleNamespace(last_update_success=True, data={"analysis": analysis})

    score = PlantCareAIHealthScoreSensor(entry, coordinator)
    status = PlantCareAIStatusSensor(entry, coordinator)
    confidence = PlantCareAIConfidenceSensor(entry, coordinator)
    diagnosis = PlantCareAIDiagnosisSensor(entry, coordinator)
    last = PlantCareAILastAnalysisSensor(entry, coordinator)
    attention = PlantCareAIAttentionRequiredBinarySensor(entry, coordinator)

    assert score.native_value == 88
    assert status.native_value == "healthy"
    assert confidence.native_value == 91
    assert diagnosis.native_value == analysis.summary
    assert diagnosis.extra_state_attributes["recommended_actions"] == [
        "Continue current watering schedule"
    ]
    assert diagnosis.extra_state_attributes["watering_recommendation"] == "monitor"
    assert last.native_value == analysis.analyzed_at
    assert attention.is_on is False
    assert attention.extra_state_attributes["urgency"] == "low"
