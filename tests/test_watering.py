from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.button import PlantCareMarkDoneButton
from custom_components.plant_care.const import (
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_WATERING_INTERVAL_DAYS,
    TASK_WATERING,
)
from custom_components.plant_care.coordinator import TaskComputed
from custom_components.plant_care.storage import PlantState
from custom_components.plant_care.watering import (
    SERVICE_GET_WATERING_QUEUE,
    SERVICE_MARK_WATERED,
    STATUS_DUE_SOON,
    STATUS_DUE_TODAY,
    STATUS_OVERDUE,
    async_mark_task_done,
    build_watering_queue,
)


def plant(
    plant_id: str,
    name: str,
    next_watering: date | None,
    *,
    last_update_success: bool = True,
):
    entry = SimpleNamespace(
        entry_id=f"entry_{plant_id}",
        data={CONF_PLANT_ID: plant_id, CONF_PLANT_NAME: name},
        options={OPT_WATERING_INTERVAL_DAYS: 7},
    )
    task = TaskComputed(
        last_done=datetime(2026, 9, 20, 8, tzinfo=UTC),
        next_due_date=next_watering,
        is_due=bool(next_watering and next_watering <= date(2026, 10, 3)),
        days_overdue=(
            max(0, (date(2026, 10, 3) - next_watering).days)
            if next_watering
            else 0
        ),
    )
    coordinator = SimpleNamespace(
        last_update_success=last_update_success,
        data={"tasks": {TASK_WATERING: task}},
    )
    return entry, coordinator


def test_overdue_plant_detection():
    queue = build_watering_queue(
        [plant("peace_lily", "Peace Lily", date(2026, 10, 1))],
        today=date(2026, 10, 3),
        due_soon_days=1,
    )

    assert queue[0]["status"] == STATUS_OVERDUE
    assert queue[0]["status_label"] == "2 days overdue"
    assert queue[0]["days_overdue"] == 2


def test_due_today_plant_detection():
    queue = build_watering_queue(
        [plant("calathea", "Calathea", date(2026, 10, 3))],
        today=date(2026, 10, 3),
        due_soon_days=1,
    )

    assert queue[0]["status"] == STATUS_DUE_TODAY
    assert queue[0]["status_label"] == "Due today"


def test_due_soon_plant_detection_uses_configurable_window():
    plants = [plant("fern", "Boston Fern", date(2026, 10, 5))]

    assert (
        build_watering_queue(
            plants,
            today=date(2026, 10, 3),
            due_soon_days=1,
        )
        == []
    )
    queue = build_watering_queue(
        plants,
        today=date(2026, 10, 3),
        due_soon_days=2,
    )
    assert queue[0]["status"] == STATUS_DUE_SOON
    assert queue[0]["status_label"] == "Due in 2 days"


def test_watering_queue_sorting():
    queue = build_watering_queue(
        [
            plant("tomorrow", "Tomorrow", date(2026, 10, 4)),
            plant("today_b", "Zebra", date(2026, 10, 3)),
            plant("overdue_one", "One", date(2026, 10, 2)),
            plant("today_a", "Aspidistra", date(2026, 10, 3)),
            plant("overdue_three", "Three", date(2026, 9, 30)),
        ],
        today=date(2026, 10, 3),
        due_soon_days=1,
    )

    assert [item["plant_id"] for item in queue] == [
        "overdue_three",
        "overdue_one",
        "today_a",
        "today_b",
        "tomorrow",
    ]


def test_plants_without_watering_data_and_unavailable_plants_are_omitted():
    queue = build_watering_queue(
        [
            plant("disabled", "Disabled", None),
            plant(
                "unavailable",
                "Unavailable",
                date(2026, 10, 1),
                last_update_success=False,
            ),
        ],
        today=date(2026, 10, 3),
        due_soon_days=1,
    )

    assert queue == []


async def test_successful_watering_updates_dates_and_queue(hass, monkeypatch):
    fixed_now = datetime(2026, 10, 3, 10, 30, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.plant_care.coordinator.dt_util.now", lambda: fixed_now
    )
    monkeypatch.setattr(
        "custom_components.plant_care.watering.dt_util.now", lambda: fixed_now
    )
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "peace_lily", CONF_PLANT_NAME: "Peace Lily"},
        options={
            **DEFAULT_OPTIONS,
            OPT_WATERING_INTERVAL_DAYS: 7,
        },
        unique_id="peace_lily",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    before = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_WATERING_QUEUE,
        {"due_soon_days": 1},
        blocking=True,
        return_response=True,
    )
    assert before["count"] == 1
    assert before["plants"][0]["status"] == STATUS_DUE_TODAY
    assert before["plants"][0]["button_entity_id"] == (
        "button.peace_lily_watering_mark_watered"
    )
    assert before["menu"] == {"Peace Lily — Due today": "peace_lily"}

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_MARK_WATERED,
        {"plant_id": "peace_lily"},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert result["last_watered"] == dt_util.as_local(fixed_now).isoformat()
    assert result["next_watering"] == "2026-10-10"
    assert result["watering_due"] is False
    state = await hass.data[DOMAIN][entry.entry_id]["storage"].get_entry_state(
        entry.entry_id
    )
    assert state.last_watered == result["last_watered"]
    next_state = hass.states.get("sensor.peace_lily_watering_next")
    assert next_state is not None
    assert next_state.state == "2026-10-10"

    after = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_WATERING_QUEUE,
        {"due_soon_days": 1},
        blocking=True,
        return_response=True,
    )
    assert after["count"] == 0
    assert after["plants"] == []


async def test_failed_watering_action_restores_previous_timestamp():
    previous = "2026-09-20T08:00:00+00:00"

    class Storage:
        last_watered = previous

        async def get_entry_state(self, entry_id):
            return PlantState(last_watered=self.last_watered)

        async def set_last_done(self, entry_id, task_type, iso_dt):
            self.last_watered = iso_dt

    storage = Storage()
    coordinator = SimpleNamespace(
        last_update_success=True,
        async_refresh=AsyncMock(side_effect=[OSError("refresh failed"), None]),
    )
    entry = SimpleNamespace(entry_id="entry_peace_lily")

    with pytest.raises(HomeAssistantError, match="Could not update"):
        await async_mark_task_done(
            entry,
            coordinator,
            storage,
            TASK_WATERING,
            now=datetime(2026, 10, 3, 10, 30, tzinfo=UTC),
        )

    assert storage.last_watered == previous
    assert coordinator.async_refresh.await_count == 2


async def test_existing_mark_watered_button_uses_shared_action(monkeypatch):
    fixed_now = datetime(2026, 10, 3, 10, 30, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.plant_care.watering.dt_util.now", lambda: fixed_now
    )

    class Storage:
        last_watered = None

        async def get_entry_state(self, entry_id):
            return PlantState(last_watered=self.last_watered)

        async def set_last_done(self, entry_id, task_type, iso_dt):
            self.last_watered = iso_dt

    entry = SimpleNamespace(
        entry_id="entry_peace_lily",
        data={CONF_PLANT_ID: "peace_lily", CONF_PLANT_NAME: "Peace Lily"},
    )
    coordinator = SimpleNamespace(
        last_update_success=True,
        async_refresh=AsyncMock(),
    )
    storage = Storage()
    button = PlantCareMarkDoneButton(
        entry,
        coordinator,
        storage,
        TASK_WATERING,
    )

    await button.async_press()

    assert button.unique_id == "peace_lily_watering_mark_watered"
    assert storage.last_watered == dt_util.as_local(fixed_now).isoformat()
    coordinator.async_refresh.assert_awaited_once_with()
