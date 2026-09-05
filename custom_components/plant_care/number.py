from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_FERTILIZING_INTERVAL_DAYS,
    OPT_HUMIDITY_MAX,
    OPT_HUMIDITY_MIN,
    OPT_LIGHT_MAX,
    OPT_LIGHT_MIN,
    OPT_MOISTURE_MAX,
    OPT_MOISTURE_MIN,
    OPT_TEMP_MAX,
    OPT_TEMP_MIN,
    OPT_WATERING_INTERVAL_DAYS,
)
from .device import PlantCareEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    plant_name = entry.data.get("plant_name", "Plant")

    async_add_entities(
        [
            # Intervals
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_WATERING_INTERVAL_DAYS,
                name=f"{plant_name} Watering Interval (days)",
                unit="d",
                min_v=0,
                max_v=60,
                step=1,
                icon="mdi:calendar-range",
            ),
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_FERTILIZING_INTERVAL_DAYS,
                name=f"{plant_name} Fertilizing Interval (days)",
                unit="d",
                min_v=0,
                max_v=365,
                step=1,
                icon="mdi:calendar-range",
            ),
            # Moisture
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_MOISTURE_MIN,
                name=f"{plant_name} Watering Moisture min (%)",
                unit="%",
                min_v=0,
                max_v=100,
                step=1,
                icon="mdi:water-percent",
            ),
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_MOISTURE_MAX,
                name=f"{plant_name} Watering Moisture max (%)",
                unit="%",
                min_v=0,
                max_v=100,
                step=1,
                icon="mdi:water-percent",
            ),
            # Humidity
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_HUMIDITY_MIN,
                name=f"{plant_name} Targets Humidity min (%)",
                unit="%",
                min_v=0,
                max_v=100,
                step=1,
                icon="mdi:water-percent",
            ),
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_HUMIDITY_MAX,
                name=f"{plant_name} Targets Humidity max (%)",
                unit="%",
                min_v=0,
                max_v=100,
                step=1,
                icon="mdi:water-percent",
            ),
            # Temp
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_TEMP_MIN,
                name=f"{plant_name} Targets Temperature min (°C)",
                unit="°C",
                min_v=-10,
                max_v=50,
                step=0.5,
                icon="mdi:thermometer",
            ),
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_TEMP_MAX,
                name=f"{plant_name} Targets Temperature max (°C)",
                unit="°C",
                min_v=-10,
                max_v=50,
                step=0.5,
                icon="mdi:thermometer",
            ),
            # Light
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_LIGHT_MIN,
                name=f"{plant_name} Targets Light min (lx)",
                unit="lx",
                min_v=0,
                max_v=100000,
                step=100,
                icon="mdi:white-balance-sunny",
            ),
            PlantCareConfigNumber(
                entry,
                coordinator,
                key=OPT_LIGHT_MAX,
                name=f"{plant_name} Targets Light max (lx)",
                unit="lx",
                min_v=0,
                max_v=100000,
                step=100,
                icon="mdi:white-balance-sunny",
            ),
        ]
    )


class PlantCareConfigNumber(PlantCareEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX  # force input fields everywhere

    def __init__(
        self,
        entry,
        coordinator,
        *,
        key: str,
        name: str,
        unit: str,
        min_v: float,
        max_v: float,
        step: float,
        icon: str,
    ):
        super().__init__(entry, coordinator)
        self._key = key
        plant_id = entry.data.get("plant_id", entry.entry_id)

        self._attr_name = name
        self._attr_unique_id = f"{plant_id}_{key}"
        self._attr_suggested_object_id = f"{plant_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = step
        self._attr_icon = icon

    @property
    def native_value(self) -> float:
        return float(self.entry.options.get(self._key, DEFAULT_OPTIONS[self._key]))

    async def async_set_native_value(self, value: float) -> None:
        new_options = dict(self.entry.options)
        new_options[self._key] = value
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        await self.coordinator.async_request_refresh()
