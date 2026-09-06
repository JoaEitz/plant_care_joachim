from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .ai.models import PlantAnalysis
from .const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_AI_ENABLED,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_MOISTURE_ENTITY_ID,
    OPT_TEMP_ENTITY_ID,
    TASK_FERTILIZING,
    TASK_WATERING,
)
from .device import PlantCareEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        # Due tasks
        PlantCareDueBinarySensor(entry, coordinator, TASK_WATERING),
        PlantCareDueBinarySensor(entry, coordinator, TASK_FERTILIZING),
        # Env bounds (disabled-by-default if no external sensor configured)
        PlantCareEnvOutOfRangeBinarySensor(entry, coordinator, "temperature"),
        PlantCareEnvOutOfRangeBinarySensor(entry, coordinator, "humidity"),
        PlantCareEnvOutOfRangeBinarySensor(entry, coordinator, "moisture"),
    ]
    if entry.options.get(OPT_AI_ENABLED, DEFAULT_OPTIONS[OPT_AI_ENABLED]):
        entities.append(PlantCareAIAttentionRequiredBinarySensor(entry, coordinator))
    async_add_entities(entities)


class PlantCareDueBinarySensor(PlantCareEntity, BinarySensorEntity):
    """Binary sensor that turns on when a given plant care task is due."""

    _attr_device_class = "problem"

    def __init__(self, entry, coordinator, task_type: str):
        super().__init__(entry, coordinator)
        self.task_type = task_type

        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")

        if task_type == TASK_WATERING:
            self._attr_name = f"{plant_name} Watering Due"
            self._attr_unique_id = f"{plant_id}_watering_due"
            self._attr_suggested_object_id = f"{plant_id}_watering_due"
            self._attr_icon = "mdi:watering-can-outline"
        else:
            self._attr_name = f"{plant_name} Fertilizing Due"
            self._attr_unique_id = f"{plant_id}_fertilizing_due"
            self._attr_suggested_object_id = f"{plant_id}_fertilizing_due"
            self._attr_icon = "mdi:bottle-tonic-outline"

    @property
    def is_on(self) -> bool | None:
        """
        Return True/False if known, None if unknown.

        Home Assistant may call this before the coordinator has data.
        """
        data: dict[str, Any] | None = self.coordinator.data
        if not data:
            return None

        tasks = data.get("tasks")
        if not isinstance(tasks, dict):
            return None

        task = tasks.get(self.task_type)
        if task is None:
            return None

        return bool(getattr(task, "is_due", False))

    @property
    def extra_state_attributes(self):
        # Safe even when coordinator.data is None or tasks missing
        data = self.coordinator.data or {}
        tasks = data.get("tasks") or {}
        t = tasks.get(self.task_type)

        if t is None:
            return {}

        next_due = getattr(t, "next_due_date", None)
        return {
            "next_due_date": next_due.isoformat() if next_due else None,
            "days_overdue": getattr(t, "days_overdue", None),
        }


class PlantCareEnvOutOfRangeBinarySensor(PlantCareEntity, BinarySensorEntity):
    """Binary sensor that turns on when the selected env sensor is out of bounds.

    UX:
    - Always created so users can discover it
    - Disabled by default if no source sensor is configured
    - Unavailable if not configured or source state invalid
    """

    _attr_device_class = "problem"

    def __init__(self, entry, coordinator, metric: str):
        super().__init__(entry, coordinator)
        self.metric = metric

        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")

        pretty = {
            "temperature": "Temperature",
            "humidity": "Humidity",
            "moisture": "Moisture",
        }[metric]

        self._attr_name = f"{plant_name} {pretty} Out of range"
        self._attr_unique_id = f"{plant_id}_{metric}_out_of_range"
        self._attr_suggested_object_id = f"{plant_id}_{metric}_out_of_range"

        # Disabled by default if no external sensor configured
        opt_key = {
            "temperature": OPT_TEMP_ENTITY_ID,
            "humidity": OPT_HUMIDITY_ENTITY_ID,
            "moisture": OPT_MOISTURE_ENTITY_ID,
        }[metric]
        is_configured = bool((entry.options.get(opt_key) or "").strip())
        self._attr_entity_registry_enabled_default = is_configured

        # Icons: default + alert
        self._icon_ok = {
            "temperature": "mdi:thermometer",
            "humidity": "mdi:water-percent",
            "moisture": "mdi:flower",
        }[metric]
        self._icon_bad = {
            "temperature": "mdi:thermometer-alert",
            "humidity": "mdi:water-alert",
            "moisture": "mdi:flower-outline",
        }[metric]

    def _metric_data(self) -> dict:
        data = (self.coordinator.data or {}).get("env", {})
        return data.get(self.metric, {})

    @property
    def available(self) -> bool:
        # out_of_range == None means unavailable (no configured sensor / invalid value)
        oor = self._metric_data().get("out_of_range")
        return oor is not None

    @property
    def is_on(self) -> bool | None:
        # Should be True/False/None (None => unavailable/unknown)
        return self._metric_data().get("out_of_range")

    @property
    def icon(self) -> str | None:
        # If unknown, show the "ok" icon (or choose whichever you prefer)
        return self._icon_bad if self.is_on is True else self._icon_ok

    @property
    def extra_state_attributes(self):
        m = self._metric_data()
        return {
            "value": m.get("value"),
            "min": m.get("min"),
            "max": m.get("max"),
            "deviation": m.get("deviation"),
        }


class PlantCareAIAttentionRequiredBinarySensor(PlantCareEntity, BinarySensorEntity):
    """Show whether the latest AI analysis recommends attention."""

    _attr_device_class = "problem"

    def __init__(self, entry, coordinator):
        super().__init__(entry, coordinator)
        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")
        self._attr_name = f"{plant_name} AI Attention Required"
        self._attr_unique_id = f"{plant_id}_ai_attention_required"
        self._attr_suggested_object_id = f"{plant_id}_ai_attention_required"
        self._attr_icon = "mdi:leaf-alert"

    @property
    def analysis(self) -> PlantAnalysis | None:
        return (self.coordinator.data or {}).get("analysis")

    @property
    def available(self) -> bool:
        return super().available and self.analysis is not None

    @property
    def is_on(self) -> bool | None:
        return self.analysis.attention_required if self.analysis else None

    @property
    def extra_state_attributes(self):
        if self.analysis is None:
            return {}
        return {
            "status": self.analysis.status,
            "urgency": self.analysis.urgency,
            "primary_issue": self.analysis.primary_issue,
        }
