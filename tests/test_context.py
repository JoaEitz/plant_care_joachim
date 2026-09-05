from datetime import UTC, datetime
from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.ai.context import PlantContextBuilder
from custom_components.plant_care.ai.models import PlantAnalysis
from custom_components.plant_care.const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DOMAIN,
    OPT_AI_HISTORY_DAYS,
    OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
    OPT_MOISTURE_ENTITY_ID,
    OPT_PLANT_SPECIES,
    OPT_WATERING_INTERVAL_DAYS,
    TASK_FERTILIZING,
    TASK_WATERING,
)
from custom_components.plant_care.coordinator import TaskComputed


def previous(score):
    return PlantAnalysis.from_ai_dict(
        {
            "health_score": score,
            "status": "watch",
            "attention_required": True,
            "confidence": 0.8,
            "primary_issue": "Drying",
            "summary": "Some stress.",
            "observations": [],
            "recommended_actions": ["Monitor"],
            "urgency": "medium",
            "watering": None,
        },
        analyzed_at=datetime(2026, 9, score % 20 + 1, tzinfo=UTC),
    )


class Storage:
    def __init__(self):
        self.limit = None

    async def async_get_analyses(self, plant_id, limit):
        self.limit = limit
        return [previous(60), previous(70), previous(80)][:limit]


class History:
    def __init__(self):
        self.days = None

    async def async_collect(self, source_entities, current_values, history_days):
        self.days = history_days
        assert source_entities == {"soil_moisture": "sensor.soil"}
        assert current_values == {"soil_moisture": 61.0}
        return {}


async def test_context_uses_configured_history_and_previous_limits(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "peace_lily", CONF_PLANT_NAME: "Peace Lily"},
        options={
            OPT_PLANT_SPECIES: "Spathiphyllum",
            OPT_MOISTURE_ENTITY_ID: "sensor.soil",
            OPT_WATERING_INTERVAL_DAYS: 7,
            OPT_AI_HISTORY_DAYS: 21,
            OPT_AI_PREVIOUS_ANALYSIS_LIMIT: 2,
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.soil", "61", {"unit_of_measurement": "%"})
    tasks = {
        TASK_WATERING: TaskComputed(None, None, True, 0),
        TASK_FERTILIZING: TaskComputed(None, None, False, 0),
    }
    coordinator = SimpleNamespace(
        data={
            "env": {"moisture": {"value": 61.0}},
            "tasks": tasks,
        }
    )
    storage = Storage()
    history = History()
    builder = PlantContextBuilder(
        hass,
        entry,
        coordinator,
        storage,
        history_reader=history,
    )

    context = await builder.async_build()

    assert context.plant["species"] == "Spathiphyllum"
    assert context.current["soil_moisture"]["value"] == 61
    assert context.care["watering"]["due"] is True
    assert len(context.previous_ai_analyses) == 2
    assert storage.limit == 2
    assert history.days == 21
