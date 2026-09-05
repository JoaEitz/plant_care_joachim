"""Recorder-backed sensor history aggregation for AI analysis."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .models import DailyMeasurement, HistoricalMeasurement

_LOGGER = logging.getLogger(__name__)

HistoryFetcher = Callable[
    [datetime, datetime, list[str]],
    Awaitable[Mapping[str, list[Any]]],
]


def _state_value_and_time(state: Any) -> tuple[Any, datetime | None]:
    if isinstance(state, Mapping):
        return (
            state.get("state"),
            state.get("last_updated") or state.get("last_changed"),
        )
    return getattr(state, "state", None), (
        getattr(state, "last_updated", None) or getattr(state, "last_changed", None)
    )


def aggregate_numeric_states(
    states: Iterable[Any],
    *,
    current: float | None = None,
) -> HistoricalMeasurement | None:
    """Aggregate numeric HA states into compact statistics and daily averages."""
    samples: list[tuple[datetime | None, float]] = []
    for state in states:
        raw_value, timestamp = _state_value_and_time(state)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        samples.append((timestamp, value))

    if not samples:
        return None

    values = [sample[1] for sample in samples]
    average = sum(values) / len(values)
    start = values[0]
    end = values[-1]
    change = end - start
    stable_threshold = max(0.5, abs(average) * 0.02)
    trend = "stable"
    if change > stable_threshold:
        trend = "rising"
    elif change < -stable_threshold:
        trend = "falling"

    daily_values: dict[str, list[float]] = defaultdict(list)
    for timestamp, value in samples:
        if not isinstance(timestamp, datetime):
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=dt_util.UTC)
        day = dt_util.as_local(timestamp).date().isoformat()
        daily_values[day].append(value)

    daily = tuple(
        DailyMeasurement(date=day, average=round(sum(items) / len(items), 2))
        for day, items in sorted(daily_values.items())
    )

    return HistoricalMeasurement(
        current=round(current, 2) if current is not None else None,
        minimum=round(min(values), 2),
        maximum=round(max(values), 2),
        average=round(average, 2),
        start=round(start, 2),
        end=round(end, 2),
        change=round(change, 2),
        trend=trend,
        samples=len(values),
        daily=daily,
    )


class RecorderHistoryReader:
    """Read relevant history through Home Assistant's recorder executor."""

    def __init__(
        self,
        hass: HomeAssistant,
        fetcher: HistoryFetcher | None = None,
    ) -> None:
        self._hass = hass
        self._fetcher = fetcher

    async def async_collect(
        self,
        source_entities: Mapping[str, str],
        current_values: Mapping[str, float],
        history_days: int,
    ) -> dict[str, HistoricalMeasurement]:
        entity_ids = list(dict.fromkeys(source_entities.values()))
        if not entity_ids or history_days <= 0:
            return {}

        end_time = dt_util.utcnow()
        start_time = end_time - timedelta(days=history_days)
        try:
            states_by_entity = await self._async_fetch(
                start_time,
                end_time,
                entity_ids,
            )
        except (KeyError, RuntimeError, TimeoutError, ImportError) as err:
            _LOGGER.warning(
                "Plant history is unavailable; continuing without it: %s", err
            )
            return {}
        except Exception as err:  # recorder/backend failures must not abort analysis
            _LOGGER.warning(
                "Unable to read plant history; continuing without it: %s",
                type(err).__name__,
            )
            return {}

        result: dict[str, HistoricalMeasurement] = {}
        for metric, entity_id in source_entities.items():
            aggregate = aggregate_numeric_states(
                states_by_entity.get(entity_id, []),
                current=current_values.get(metric),
            )
            if aggregate is not None:
                result[metric] = aggregate
        return result

    async def _async_fetch(
        self,
        start_time: datetime,
        end_time: datetime,
        entity_ids: list[str],
    ) -> Mapping[str, list[Any]]:
        if self._fetcher is not None:
            return await self._fetcher(start_time, end_time, entity_ids)

        if "recorder" not in self._hass.config.components:
            raise RuntimeError("recorder is not loaded")

        from homeassistant.components.recorder import get_instance, history

        query = partial(
            history.get_significant_states,
            self._hass,
            start_time,
            end_time,
            entity_ids=entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=True,
        )
        return await get_instance(self._hass).async_add_executor_job(query)
