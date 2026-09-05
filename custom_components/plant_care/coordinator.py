from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PLANT_ID,
    DEFAULT_OPTIONS,
    OPT_CONDUCTIVITY_ENTITY_ID,
    OPT_FERTILIZING_INTERVAL_DAYS,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_HUMIDITY_MAX,
    OPT_HUMIDITY_MIN,
    OPT_LIGHT_ENTITY_ID,
    OPT_LIGHT_MAX,
    OPT_LIGHT_MIN,
    OPT_MOISTURE_ENTITY_ID,
    OPT_MOISTURE_MAX,
    OPT_MOISTURE_MIN,
    OPT_TEMP_ENTITY_ID,
    OPT_TEMP_MAX,
    OPT_TEMP_MIN,
    OPT_WATERING_INTERVAL_DAYS,
    TASK_FERTILIZING,
    TASK_WATERING,
)
from .storage import PlantCareStorage

_LOGGER = logging.getLogger(__name__)


@dataclass
class TaskComputed:
    last_done: datetime | None
    next_due_date: date | None
    is_due: bool
    days_overdue: int


class PlantCareCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for plant care.

    Updates:
    - every 15 minutes (environment checks)
    - plus manual refresh via buttons/config changes (async_refresh())
    - plus your daily trigger at 03:00 (handled in __init__.py)
    """

    def __init__(self, hass: HomeAssistant, entry, storage: PlantCareStorage) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"plant_care_{entry.entry_id}",
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry
        self.storage = storage

    def get_number(self, key: str) -> float:
        """Return numeric option/config values (floats/ints) with defaults."""
        return float(self.entry.options.get(key, DEFAULT_OPTIONS[key]))

    async def _async_update_data(self) -> dict[str, Any]:
        # Load persisted last_* values
        state = await self.storage.get_entry_state(self.entry.entry_id)

        now = dt_util.now()
        today = dt_util.as_local(now).date()

        def parse_iso(iso: str | None) -> datetime | None:
            if not iso:
                return None
            try:
                dt = dt_util.parse_datetime(iso)
                return dt_util.as_local(dt) if dt else None
            except Exception:
                return None

        last_watered_dt = parse_iso(state.last_watered)
        last_fertilized_dt = parse_iso(state.last_fertilized)

        def compute_task(
            last_done: datetime | None, interval_days: int
        ) -> TaskComputed:
            # interval_days == 0 means "disabled"
            if interval_days <= 0:
                return TaskComputed(
                    last_done=last_done,
                    next_due_date=None,
                    is_due=False,
                    days_overdue=0,
                )

            if last_done is None:
                # Never done -> due immediately
                return TaskComputed(
                    last_done=None,
                    next_due_date=today,
                    is_due=True,
                    days_overdue=0,
                )

            last_done_date = dt_util.as_local(last_done).date()
            next_due = last_done_date + timedelta(days=interval_days)
            is_due = today >= next_due
            overdue = (today - next_due).days if is_due else 0

            return TaskComputed(
                last_done=last_done,
                next_due_date=next_due,
                is_due=is_due,
                days_overdue=overdue,
            )

        def _read_float_state(entity_id: str) -> float | None:
            if not entity_id:
                return None
            st = self.hass.states.get(entity_id)
            if st is None:
                return None
            try:
                value = float(st.state)
            except (ValueError, TypeError):
                return None
            return value if math.isfinite(value) else None

        def _compute_bounds(
            value: float | None, min_v: float, max_v: float
        ) -> dict[str, Any]:
            # if value is None -> unavailable
            if value is None:
                return {
                    "value": None,
                    "min": min_v,
                    "max": max_v,
                    "out_of_range": None,  # None => unavailable
                    "deviation": None,
                }

            if value < min_v:
                return {
                    "value": value,
                    "min": min_v,
                    "max": max_v,
                    "out_of_range": True,
                    "deviation": float(min_v - value),  # below min
                }
            if value > max_v:
                return {
                    "value": value,
                    "min": min_v,
                    "max": max_v,
                    "out_of_range": True,
                    "deviation": float(value - max_v),  # above max
                }
            return {
                "value": value,
                "min": min_v,
                "max": max_v,
                "out_of_range": False,
                "deviation": 0.0,
            }

        # --- Task intervals (0 disables) ---
        water_interval = int(self.get_number(OPT_WATERING_INTERVAL_DAYS))
        fert_interval = int(self.get_number(OPT_FERTILIZING_INTERVAL_DAYS))

        watering = compute_task(last_watered_dt, water_interval)
        fertilizing = compute_task(last_fertilized_dt, fert_interval)

        # --- External env sensors (optional) ---
        temp_entity = (self.entry.options.get(OPT_TEMP_ENTITY_ID) or "").strip()
        humidity_entity = (self.entry.options.get(OPT_HUMIDITY_ENTITY_ID) or "").strip()
        moisture_entity = (self.entry.options.get(OPT_MOISTURE_ENTITY_ID) or "").strip()
        light_entity = (self.entry.options.get(OPT_LIGHT_ENTITY_ID) or "").strip()
        conductivity_entity = (
            self.entry.options.get(OPT_CONDUCTIVITY_ENTITY_ID) or ""
        ).strip()

        temp_value = _read_float_state(temp_entity)
        humidity_value = _read_float_state(humidity_entity)
        moisture_value = _read_float_state(moisture_entity)
        light_value = _read_float_state(light_entity)
        conductivity_value = _read_float_state(conductivity_entity)

        temp_min = float(self.get_number(OPT_TEMP_MIN))
        temp_max = float(self.get_number(OPT_TEMP_MAX))
        humidity_min = float(self.get_number(OPT_HUMIDITY_MIN))
        humidity_max = float(self.get_number(OPT_HUMIDITY_MAX))
        moisture_min = float(self.get_number(OPT_MOISTURE_MIN))
        moisture_max = float(self.get_number(OPT_MOISTURE_MAX))
        light_min = float(self.get_number(OPT_LIGHT_MIN))
        light_max = float(self.get_number(OPT_LIGHT_MAX))

        env = {
            "temperature": _compute_bounds(temp_value, temp_min, temp_max),
            "humidity": _compute_bounds(humidity_value, humidity_min, humidity_max),
            "moisture": _compute_bounds(moisture_value, moisture_min, moisture_max),
            "illuminance": _compute_bounds(light_value, light_min, light_max),
            "conductivity": {
                "value": conductivity_value,
                "min": None,
                "max": None,
                "out_of_range": None,
                "deviation": None,
            },
        }

        plant_name = self.entry.data.get("plant_name", "Plant")
        plant_id = str(self.entry.data.get(CONF_PLANT_ID, self.entry.entry_id))
        analysis = await self.storage.async_get_latest_analysis(plant_id)

        return {
            "plant_name": plant_name,
            "tasks": {
                TASK_WATERING: watering,
                TASK_FERTILIZING: fertilizing,
            },
            "env": env,
            "analysis": analysis,
        }
