from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .ai.models import PlantAnalysis
from .const import (
    DOMAIN,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_MOISTURE_ENTITY_ID,
    OPT_TEMP_ENTITY_ID,
    TASK_FERTILIZING,
    TASK_WATERING,
)
from .device import PlantCareEntity


def _get_task(data: dict[str, Any] | None, task_type: str):
    """Safely fetch a task from coordinator data (data may be None during startup)."""
    if not data:
        return None
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        return None
    return tasks.get(task_type)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            # Task sensors
            PlantCareLastDoneSensor(entry, coordinator, TASK_WATERING),
            PlantCareNextDueDateSensor(entry, coordinator, TASK_WATERING),
            PlantCareLastDoneSensor(entry, coordinator, TASK_FERTILIZING),
            PlantCareNextDueDateSensor(entry, coordinator, TASK_FERTILIZING),
            # Environment deviation sensors. Disabled by default without a source.
            PlantCareEnvDeviationSensor(
                entry, coordinator, "temperature", unit="°C", icon="mdi:thermometer"
            ),
            PlantCareEnvDeviationSensor(
                entry, coordinator, "humidity", unit="%", icon="mdi:water-percent"
            ),
            PlantCareEnvDeviationSensor(
                entry, coordinator, "moisture", unit="%", icon="mdi:flower"
            ),
            PlantCareAIHealthScoreSensor(entry, coordinator),
            PlantCareAIStatusSensor(entry, coordinator),
            PlantCareAIConfidenceSensor(entry, coordinator),
            PlantCareAIDiagnosisSensor(entry, coordinator),
            PlantCareAILastAnalysisSensor(entry, coordinator),
        ]
    )


class PlantCareLastDoneSensor(PlantCareEntity, SensorEntity):
    _attr_device_class = "timestamp"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry, coordinator, task_type: str):
        super().__init__(entry, coordinator)
        self.task_type = task_type
        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")

        if task_type == TASK_WATERING:
            self._attr_name = f"{plant_name} Watering Last"
            self._attr_unique_id = f"{plant_id}_watering_last"
            self._attr_suggested_object_id = f"{plant_id}_watering_last"
            self._attr_icon = "mdi:watering-can-outline"
        else:
            self._attr_name = f"{plant_name} Fertilizing Last"
            self._attr_unique_id = f"{plant_id}_fertilizing_last"
            self._attr_suggested_object_id = f"{plant_id}_fertilizing_last"
            self._attr_icon = "mdi:bottle-tonic-outline"

    @property
    def native_value(self):
        task = _get_task(self.coordinator.data, self.task_type)
        if task is None:
            return None  # unknown until coordinator has data

        # Expecting a datetime (device_class timestamp)
        return getattr(task, "last_done", None)


class PlantCareNextDueDateSensor(PlantCareEntity, SensorEntity):
    # We'll expose as date string YYYY-MM-DD (simple & stable)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry, coordinator, task_type: str):
        super().__init__(entry, coordinator)
        self.task_type = task_type
        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")

        if task_type == TASK_WATERING:
            self._attr_name = f"{plant_name} Watering Next"
            self._attr_unique_id = f"{plant_id}_watering_next"
            self._attr_suggested_object_id = f"{plant_id}_watering_next"
            self._attr_icon = "mdi:calendar"
        else:
            self._attr_name = f"{plant_name} Fertilizing Next"
            self._attr_unique_id = f"{plant_id}_fertilizing_next"
            self._attr_suggested_object_id = f"{plant_id}_fertilizing_next"
            self._attr_icon = "mdi:calendar"

    @property
    def native_value(self):
        task = _get_task(self.coordinator.data, self.task_type)
        if task is None:
            return None  # unknown until coordinator has data

        next_due = getattr(task, "next_due_date", None)
        return next_due.isoformat() if next_due else None


class PlantCareEnvDeviationSensor(PlantCareEntity, SensorEntity):
    """Shows how far the external sensor value is outside the configured bounds.

    - 0.0: within bounds
    - >0: deviation outside bounds
    - unavailable: no external sensor configured or invalid value

    UX:
    - Always created so users can discover it
    - Disabled by default if no source sensor is configured
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry, coordinator, metric: str, *, unit: str, icon: str):
        super().__init__(entry, coordinator)
        self.metric = metric

        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")

        pretty = {
            "temperature": "Temperature",
            "humidity": "Humidity",
            "moisture": "Moisture",
        }[metric]

        self._attr_name = f"{plant_name} {pretty} Deviation"
        self._attr_unique_id = f"{plant_id}_{metric}_deviation"
        self._attr_suggested_object_id = f"{plant_id}_{metric}_deviation"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

        # Disabled by default if no external sensor configured
        opt_key = {
            "temperature": OPT_TEMP_ENTITY_ID,
            "humidity": OPT_HUMIDITY_ENTITY_ID,
            "moisture": OPT_MOISTURE_ENTITY_ID,
        }[metric]
        is_configured = bool((entry.options.get(opt_key) or "").strip())
        self._attr_entity_registry_enabled_default = is_configured

    def _metric_data(self) -> dict:
        data = (self.coordinator.data or {}).get("env", {})
        return data.get(self.metric, {})

    @property
    def available(self) -> bool:
        # deviation == None means unavailable (no configured sensor / invalid value)
        dev = self._metric_data().get("deviation")
        return dev is not None

    @property
    def native_value(self):
        return self._metric_data().get("deviation")

    @property
    def extra_state_attributes(self):
        m = self._metric_data()
        return {
            "value": m.get("value"),
            "min": m.get("min"),
            "max": m.get("max"),
        }


class PlantCareAnalysisSensor(PlantCareEntity, SensorEntity):
    """Base class for entities backed by the latest stored analysis."""

    def __init__(self, entry, coordinator, suffix: str, name: str, icon: str):
        super().__init__(entry, coordinator)
        plant_id = entry.data.get("plant_id", entry.entry_id)
        plant_name = entry.data.get("plant_name", "Plant")
        self._attr_name = f"{plant_name} {name}"
        self._attr_unique_id = f"{plant_id}_{suffix}"
        self._attr_suggested_object_id = f"{plant_id}_{suffix}"
        self._attr_icon = icon

    @property
    def analysis(self) -> PlantAnalysis | None:
        return (self.coordinator.data or {}).get("analysis")

    @property
    def available(self) -> bool:
        return super().available and self.analysis is not None


class PlantCareAIHealthScoreSensor(PlantCareAnalysisSensor):
    def __init__(self, entry, coordinator):
        super().__init__(
            entry, coordinator, "ai_health_score", "AI Health Score", "mdi:leaf"
        )

    @property
    def native_value(self):
        return self.analysis.health_score if self.analysis else None


class PlantCareAIStatusSensor(PlantCareAnalysisSensor):
    def __init__(self, entry, coordinator):
        super().__init__(
            entry, coordinator, "ai_status", "AI Status", "mdi:heart-pulse"
        )

    @property
    def native_value(self):
        return self.analysis.status if self.analysis else None


class PlantCareAIConfidenceSensor(PlantCareAnalysisSensor):
    _attr_native_unit_of_measurement = "%"
    _attr_suggested_display_precision = 0

    def __init__(self, entry, coordinator):
        super().__init__(
            entry, coordinator, "ai_confidence", "AI Confidence", "mdi:gauge"
        )

    @property
    def native_value(self):
        return round(self.analysis.confidence * 100) if self.analysis else None


class PlantCareAIDiagnosisSensor(PlantCareAnalysisSensor):
    def __init__(self, entry, coordinator):
        super().__init__(
            entry, coordinator, "ai_diagnosis", "AI Diagnosis", "mdi:stethoscope"
        )

    @property
    def native_value(self):
        if not self.analysis:
            return None
        return (self.analysis.primary_issue or self.analysis.summary)[:255]

    @property
    def extra_state_attributes(self):
        analysis = self.analysis
        if analysis is None:
            return {}
        return {
            "primary_issue": analysis.primary_issue,
            "summary": analysis.summary,
            "observations": list(analysis.observations),
            "recommended_actions": list(analysis.recommended_actions),
            "urgency": analysis.urgency,
            "watering_recommendation": (
                analysis.watering.recommendation if analysis.watering else None
            ),
            "watering_reason": (
                analysis.watering.reason if analysis.watering else None
            ),
        }


class PlantCareAILastAnalysisSensor(PlantCareAnalysisSensor):
    _attr_device_class = "timestamp"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry, coordinator):
        super().__init__(
            entry,
            coordinator,
            "ai_last_analysis",
            "AI Last Analysis",
            "mdi:clock-check-outline",
        )

    @property
    def native_value(self):
        return self.analysis.analyzed_at if self.analysis else None
