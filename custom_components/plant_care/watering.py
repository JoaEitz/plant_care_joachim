"""Watering actions and the dynamic watering queue."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_WATERING_INTERVAL_DAYS,
    TASK_WATERING,
)
from .service_helpers import PLANT_TARGET_SCHEMA, resolve_plant_entry

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_WATERING_QUEUE = "get_watering_queue"
SERVICE_MARK_WATERED = "mark_watered"

CONF_DUE_SOON_DAYS = "due_soon_days"
CONF_LIMIT = "limit"
DEFAULT_DUE_SOON_DAYS = 1
DEFAULT_QUEUE_LIMIT = 10

STATUS_OVERDUE = "overdue"
STATUS_DUE_TODAY = "due_today"
STATUS_DUE_SOON = "due_soon"

GET_WATERING_QUEUE_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_DUE_SOON_DAYS, default=DEFAULT_DUE_SOON_DAYS
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
        vol.Optional(CONF_LIMIT, default=DEFAULT_QUEUE_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
    }
)

MARK_WATERED_SCHEMA = vol.Schema(PLANT_TARGET_SCHEMA)


def watering_status(
    next_watering: date,
    *,
    today: date,
    due_soon_days: int,
) -> tuple[str, str, int] | None:
    """Return status, display label, and signed days until watering."""
    days_until_due = (next_watering - today).days
    if days_until_due < 0:
        days_overdue = abs(days_until_due)
        unit = "day" if days_overdue == 1 else "days"
        return STATUS_OVERDUE, f"{days_overdue} {unit} overdue", days_until_due
    if days_until_due == 0:
        return STATUS_DUE_TODAY, "Due today", days_until_due
    if days_until_due > due_soon_days:
        return None
    if days_until_due == 1:
        return STATUS_DUE_SOON, "Due tomorrow", days_until_due
    return STATUS_DUE_SOON, f"Due in {days_until_due} days", days_until_due


def build_watering_queue(
    plants: Iterable[tuple[Any, Any]],
    *,
    today: date,
    due_soon_days: int,
    limit: int | None = None,
    button_entity_ids: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build a sorted queue from loaded config entries and coordinator data."""
    items: list[dict[str, Any]] = []
    button_entity_ids = button_entity_ids or {}

    for entry, coordinator in plants:
        if getattr(coordinator, "last_update_success", True) is False:
            continue
        data = getattr(coordinator, "data", None)
        if not isinstance(data, dict):
            continue
        tasks = data.get("tasks")
        if not isinstance(tasks, dict):
            continue
        task = tasks.get(TASK_WATERING)
        next_watering = getattr(task, "next_due_date", None)
        if not isinstance(next_watering, date):
            continue

        status = watering_status(
            next_watering,
            today=today,
            due_soon_days=due_soon_days,
        )
        if status is None:
            continue
        status_name, status_label, days_until_due = status

        plant_id = str(entry.data.get(CONF_PLANT_ID, entry.entry_id))
        plant_name = str(entry.data.get(CONF_PLANT_NAME, "Plant"))
        last_done = getattr(task, "last_done", None)
        items.append(
            {
                "plant_id": plant_id,
                "config_entry_id": entry.entry_id,
                "name": plant_name,
                "status": status_name,
                "status_label": status_label,
                "days_until_due": days_until_due,
                "days_overdue": max(0, -days_until_due),
                "last_watered": (
                    last_done.isoformat() if isinstance(last_done, datetime) else None
                ),
                "next_watering": next_watering.isoformat(),
                "watering_interval_days": int(
                    entry.options.get(
                        OPT_WATERING_INTERVAL_DAYS,
                        DEFAULT_OPTIONS[OPT_WATERING_INTERVAL_DAYS],
                    )
                ),
                "button_entity_id": button_entity_ids.get(entry.entry_id),
            }
        )

    priority = {
        STATUS_OVERDUE: 0,
        STATUS_DUE_TODAY: 1,
        STATUS_DUE_SOON: 2,
    }
    items.sort(
        key=lambda item: (
            priority[item["status"]],
            item["next_watering"],
            item["name"].casefold(),
            item["plant_id"],
        )
    )
    return items if limit is None else items[:limit]


async def async_mark_task_done(
    entry: Any,
    coordinator: Any,
    storage: Any,
    task_type: str,
    *,
    now: datetime | None = None,
) -> str:
    """Persist a completed task and refresh its existing coordinator.

    If the refresh fails, restore the prior stored timestamp so a failed action
    cannot later appear as a successful watering.
    """
    previous_state = await storage.get_entry_state(entry.entry_id)
    previous_value = (
        previous_state.last_watered
        if task_type == TASK_WATERING
        else previous_state.last_fertilized
    )
    completed_at = dt_util.as_local(now or dt_util.now()).isoformat()

    try:
        await storage.set_last_done(entry.entry_id, task_type, completed_at)
        await coordinator.async_refresh()
        if getattr(coordinator, "last_update_success", True) is False:
            raise HomeAssistantError("Plant Care could not refresh the plant state")
    except Exception as err:
        try:
            await storage.set_last_done(entry.entry_id, task_type, previous_value)
            await coordinator.async_refresh()
        except Exception as rollback_err:
            _LOGGER.error(
                "Could not restore task state for Plant Care entry %s "
                "after failure: %s",
                entry.entry_id,
                rollback_err,
            )
        raise HomeAssistantError("Could not update the plant care task") from err

    return completed_at


def watering_queue_response(
    hass: HomeAssistant,
    *,
    due_soon_days: int,
    limit: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the current queue in a Home Assistant and Shortcuts-friendly shape."""
    generated_at = dt_util.as_local(now or dt_util.now())
    domain_data = hass.data.get(DOMAIN) or {}
    registry = er.async_get(hass)
    plants: list[tuple[Any, Any]] = []
    button_entity_ids: dict[str, str] = {}

    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = domain_data.get(entry.entry_id)
        if not isinstance(runtime, dict):
            continue
        coordinator = runtime.get("coordinator")
        if coordinator is None:
            continue
        plants.append((entry, coordinator))
        plant_id = str(entry.data.get(CONF_PLANT_ID, entry.entry_id))
        button_entity_id = registry.async_get_entity_id(
            "button",
            DOMAIN,
            f"{plant_id}_watering_mark_watered",
        )
        if button_entity_id:
            button_entity_ids[entry.entry_id] = button_entity_id

    queue = build_watering_queue(
        plants,
        today=generated_at.date(),
        due_soon_days=due_soon_days,
        limit=limit,
        button_entity_ids=button_entity_ids,
    )
    menu: dict[str, str] = {}
    for item in queue:
        label = f"{item['name']} — {item['status_label']}"
        if label in menu:
            label = f"{label} ({item['plant_id']})"
        menu[label] = item["plant_id"]

    return {
        "generated_at": generated_at.isoformat(),
        "due_soon_days": due_soon_days,
        "count": len(queue),
        "plants": queue,
        "menu": menu,
    }


def async_register_watering_services(hass: HomeAssistant) -> None:
    """Register domain-level watering services once."""

    async def async_get_watering_queue(call: ServiceCall) -> dict[str, Any]:
        return watering_queue_response(
            hass,
            due_soon_days=int(call.data[CONF_DUE_SOON_DAYS]),
            limit=int(call.data[CONF_LIMIT]),
        )

    async def async_mark_watered(call: ServiceCall) -> dict[str, Any]:
        entry = resolve_plant_entry(hass, call.data)
        runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
        coordinator = runtime.get("coordinator")
        storage = runtime.get("storage")
        if coordinator is None or storage is None:
            raise HomeAssistantError("The selected Plant Care entry is not loaded")

        completed_at = await async_mark_task_done(
            entry,
            coordinator,
            storage,
            TASK_WATERING,
        )
        task = ((coordinator.data or {}).get("tasks") or {}).get(TASK_WATERING)
        next_watering = getattr(task, "next_due_date", None)
        return {
            "plant_id": str(entry.data.get(CONF_PLANT_ID, entry.entry_id)),
            "name": str(entry.data.get(CONF_PLANT_NAME, "Plant")),
            "last_watered": completed_at,
            "next_watering": (
                next_watering.isoformat() if isinstance(next_watering, date) else None
            ),
            "watering_due": bool(getattr(task, "is_due", False)),
        }

    if not hass.services.has_service(DOMAIN, SERVICE_GET_WATERING_QUEUE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WATERING_QUEUE,
            async_get_watering_queue,
            schema=GET_WATERING_QUEUE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_WATERED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_WATERED,
            async_mark_watered,
            schema=MARK_WATERED_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
