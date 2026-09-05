from datetime import UTC, datetime, timedelta

from custom_components.plant_care.ai.models import PlantAnalysis
from custom_components.plant_care.const import STORAGE_KEY
from custom_components.plant_care.storage import PlantCareStorage


def analysis(score: int, analyzed_at: datetime) -> PlantAnalysis:
    return PlantAnalysis.from_ai_dict(
        {
            "health_score": score,
            "status": "healthy",
            "attention_required": False,
            "confidence": 0.9,
            "primary_issue": None,
            "summary": "No visible acute stress.",
            "observations": ["Leaves appear normal"],
            "recommended_actions": ["Continue current care"],
            "urgency": "low",
            "watering": None,
        },
        analyzed_at=analyzed_at,
    )


async def test_storage_save_load_and_previous_analysis_limit(hass):
    store = PlantCareStorage(hass)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for index in range(5):
        await store.async_store_analysis(
            "peace_lily", analysis(70 + index, start + timedelta(days=index))
        )

    recent = await store.async_get_analyses("peace_lily", limit=3)
    assert [item.health_score for item in recent] == [74, 73, 72]
    assert await store.async_get_analyses("peace_lily", limit=0) == []

    restarted_store = PlantCareStorage(hass)
    restored = await restarted_store.async_get_latest_analysis("peace_lily")
    assert restored is not None
    assert restored.health_score == 74


async def test_storage_bounds_history(hass):
    store = PlantCareStorage(hass)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for index in range(25):
        await store.async_store_analysis(
            "monstera", analysis(index, start + timedelta(hours=index))
        )

    items = await store.async_get_analyses("monstera")
    assert len(items) == 20
    assert items[0].health_score == 24
    assert items[-1].health_score == 5


async def test_storage_migrates_existing_care_state(hass, hass_storage):
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"entries": {"old_entry": {"last_watered": "2026-09-01"}}},
    }
    storage = PlantCareStorage(hass)

    loaded = await storage.async_load()

    assert loaded["entries"]["old_entry"]["last_watered"] == "2026-09-01"
    assert loaded["analyses"] == {}
