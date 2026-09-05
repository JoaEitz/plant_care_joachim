"""Build complete plant context for AI health analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_OPTIONS,
    OPT_AI_HISTORY_DAYS,
    OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
    OPT_CONDUCTIVITY_ENTITY_ID,
    OPT_FERTILIZING_INTERVAL_DAYS,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_LIGHT_ENTITY_ID,
    OPT_MOISTURE_ENTITY_ID,
    OPT_PLANT_SPECIES,
    OPT_TEMP_ENTITY_ID,
    OPT_WATERING_INTERVAL_DAYS,
    TASK_FERTILIZING,
    TASK_WATERING,
)
from ..coordinator import PlantCareCoordinator
from ..storage import PlantCareStorage
from .history import RecorderHistoryReader
from .models import PlantAnalysisContext

SENSOR_CONTEXT: dict[str, tuple[str, str | None]] = {
    "temperature": (OPT_TEMP_ENTITY_ID, "°C"),
    "humidity": (OPT_HUMIDITY_ENTITY_ID, "%"),
    "soil_moisture": (OPT_MOISTURE_ENTITY_ID, "%"),
    "illuminance": (OPT_LIGHT_ENTITY_ID, "lx"),
    "conductivity": (OPT_CONDUCTIVITY_ENTITY_ID, None),
}


class PlantContextBuilder:
    """Combine entry metadata, live state, care state, and compact history."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: PlantCareCoordinator,
        storage: PlantCareStorage,
        history_reader: RecorderHistoryReader | None = None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._storage = storage
        self._history_reader = history_reader or RecorderHistoryReader(hass)

    async def async_build(self) -> PlantAnalysisContext:
        plant_id = str(self._entry.data.get(CONF_PLANT_ID, self._entry.entry_id))
        plant: dict[str, Any] = {
            "id": plant_id,
            "name": self._entry.data.get(CONF_PLANT_NAME, "Plant"),
        }
        species = str(self._entry.options.get(OPT_PLANT_SPECIES, "") or "").strip()
        if species:
            plant["species"] = species
        if area_name := self._get_area_name():
            plant["location"] = area_name

        coordinator_data = self._coordinator.data or {}
        env_data = coordinator_data.get("env") or {}
        current: dict[str, Any] = {}
        current_values: dict[str, float] = {}
        source_entities: dict[str, str] = {}

        for metric, (option_key, unit) in SENSOR_CONTEXT.items():
            entity_id = str(self._entry.options.get(option_key, "") or "").strip()
            internal_metric = "moisture" if metric == "soil_moisture" else metric
            value = (env_data.get(internal_metric) or {}).get("value")
            if entity_id:
                source_entities[metric] = entity_id
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_value = float(value)
                current_values[metric] = numeric_value
                value_context: dict[str, Any] = {
                    "value": numeric_value,
                    "entity_id": entity_id,
                }
                source_state = self._hass.states.get(entity_id) if entity_id else None
                measured_unit = (
                    source_state.attributes.get("unit_of_measurement")
                    if source_state is not None
                    else None
                )
                if measured_unit or unit:
                    value_context["unit"] = measured_unit or unit
                current[metric] = value_context

        care = self._build_care_context(coordinator_data)
        history_days = int(
            self._entry.options.get(
                OPT_AI_HISTORY_DAYS, DEFAULT_OPTIONS[OPT_AI_HISTORY_DAYS]
            )
        )
        history = await self._history_reader.async_collect(
            source_entities,
            current_values,
            history_days,
        )

        previous_limit = int(
            self._entry.options.get(
                OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
                DEFAULT_OPTIONS[OPT_AI_PREVIOUS_ANALYSIS_LIMIT],
            )
        )
        previous = await self._storage.async_get_analyses(
            plant_id,
            limit=previous_limit,
        )

        return PlantAnalysisContext(
            plant=plant,
            current=current,
            care=care,
            history=history,
            previous_ai_analyses=tuple(
                analysis.to_compact_context() for analysis in reversed(previous)
            ),
        )

    def _build_care_context(self, coordinator_data: dict[str, Any]) -> dict[str, Any]:
        tasks = coordinator_data.get("tasks") or {}
        result: dict[str, Any] = {}
        for task_type, interval_key in (
            (TASK_WATERING, OPT_WATERING_INTERVAL_DAYS),
            (TASK_FERTILIZING, OPT_FERTILIZING_INTERVAL_DAYS),
        ):
            task = tasks.get(task_type)
            interval = int(
                self._entry.options.get(interval_key, DEFAULT_OPTIONS[interval_key])
            )
            task_context: dict[str, Any] = {
                "enabled": interval > 0,
                "interval_days": interval,
            }
            if task is not None:
                last_done = getattr(task, "last_done", None)
                if isinstance(last_done, datetime):
                    task_context["last_done"] = last_done.isoformat()
                    task_context["days_since"] = max(
                        0,
                        (
                            dt_util.as_local(dt_util.now()).date()
                            - dt_util.as_local(last_done).date()
                        ).days,
                    )
                task_context["due"] = bool(getattr(task, "is_due", False))
                task_context["days_overdue"] = int(getattr(task, "days_overdue", 0))
                next_due = getattr(task, "next_due_date", None)
                if next_due is not None:
                    task_context["next_due_date"] = next_due.isoformat()
            result[task_type] = task_context
        return result

    def _get_area_name(self) -> str | None:
        device_registry = dr.async_get(self._hass)
        area_registry = ar.async_get(self._hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, self._entry.entry_id
        ):
            if device.area_id and (
                area := area_registry.async_get_area(device.area_id)
            ):
                return area.name
        return None
