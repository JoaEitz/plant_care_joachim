from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.plant_care.ai.history import (
    RecorderHistoryReader,
    aggregate_numeric_states,
)


def state(value, timestamp):
    return SimpleNamespace(state=value, last_updated=timestamp)


def test_history_aggregation_and_falling_trend():
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    result = aggregate_numeric_states(
        [
            state("79", start),
            state("unknown", start + timedelta(hours=1)),
            state("60", start + timedelta(days=1)),
            state("61", start + timedelta(days=1, hours=2)),
        ],
        current=61,
    )

    assert result is not None
    assert result.minimum == 60
    assert result.maximum == 79
    assert result.average == pytest.approx(66.67)
    assert result.change == -18
    assert result.trend == "falling"
    assert result.samples == 3
    assert len(result.daily) == 2


def test_history_stable_trend_and_no_numeric_samples():
    now = datetime.now(UTC)
    stable = aggregate_numeric_states([state("50", now), state("50.4", now)])
    assert stable is not None
    assert stable.trend == "stable"
    assert aggregate_numeric_states([state("unavailable", now)]) is None


async def test_recorder_unavailable_does_not_fail(hass):
    reader = RecorderHistoryReader(hass)
    result = await reader.async_collect(
        {"soil_moisture": "sensor.soil"},
        {"soil_moisture": 55},
        14,
    )
    assert result == {}
