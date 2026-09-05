from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from tests.test_manager import result


async def test_entry_setup_creates_ai_entities_and_unloads(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "test_plant", CONF_PLANT_NAME: "Test Plant"},
        options=dict(DEFAULT_OPTIONS),
        unique_id="test_plant",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("button.test_plant_ai_analyze") is not None
    assert hass.states.get("sensor.test_plant_ai_health_score") is not None
    assert hass.states.get("binary_sensor.test_plant_ai_attention_required") is not None

    runtime = hass.data[DOMAIN][entry.entry_id]
    await runtime["storage"].async_store_analysis("test_plant", result())
    await runtime["coordinator"].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_plant_ai_health_score").state == "88"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_plant_ai_health_score").state == "88"


async def test_existing_create_service_keeps_duplicate_ids_stable(hass):
    assert await async_setup_component(hass, DOMAIN, {})

    await hass.services.async_call(
        DOMAIN,
        "create_plant",
        {"plant_name": "Peace Lily", "plant_species": "Spathiphyllum"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "create_plant",
        {"plant_name": "Peace Lily"},
        blocking=True,
    )

    entries = hass.config_entries.async_entries(DOMAIN)
    assert [entry.unique_id for entry in entries] == ["peace_lily", "peace_lily_2"]
    assert entries[0].options["plant_species"] == "Spathiphyllum"
