from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .ai.errors import InvalidAnalysisError
from .ai.models import PlantAnalysis
from .const import (
    MAX_AI_ANALYSES_PER_PLANT,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
    TASK_FERTILIZING,
    TASK_WATERING,
)


@dataclass
class PlantState:
    last_watered: str | None = None  # ISO datetime string
    last_fertilized: str | None = None  # ISO datetime string


class PlantCareStore(Store[dict[str, Any]]):
    """Versioned store which preserves the version 1 care-state payload."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        if old_major_version != STORAGE_VERSION:
            raise NotImplementedError

        migrated = dict(old_data)
        migrated.setdefault("entries", {})
        migrated.setdefault("analyses", {})
        return migrated


class PlantCareStorage:
    """Persist care timestamps and bounded analyses for all plant entries."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = PlantCareStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def async_load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = await self._store.async_load() or {
                "entries": {},
                "analyses": {},
            }
            if not isinstance(self._data.get("entries"), dict):
                self._data["entries"] = {}
            if not isinstance(self._data.get("analyses"), dict):
                self._data["analyses"] = {}
        return self._data

    async def async_save(self) -> None:
        if self._data is None:
            return
        await self._store.async_save(self._data)

    async def get_entry_state(self, entry_id: str) -> PlantState:
        data = await self.async_load()
        entry = data["entries"].get(entry_id, {})
        return PlantState(
            last_watered=entry.get("last_watered"),
            last_fertilized=entry.get("last_fertilized"),
        )

    async def set_last_done(self, entry_id: str, task_type: str, iso_dt: str) -> None:
        async with self._lock:
            data = await self.async_load()
            entry = data["entries"].setdefault(entry_id, {})
            if task_type == TASK_WATERING:
                entry["last_watered"] = iso_dt
            elif task_type == TASK_FERTILIZING:
                entry["last_fertilized"] = iso_dt
            else:
                raise ValueError(f"Unknown task_type: {task_type}")

            await self.async_save()

    async def async_get_analyses(
        self,
        plant_id: str,
        limit: int | None = None,
    ) -> list[PlantAnalysis]:
        """Return valid stored analyses, newest first."""
        if limit is not None and limit <= 0:
            return []
        data = await self.async_load()
        raw_items = data["analyses"].get(plant_id, [])
        if not isinstance(raw_items, list):
            return []
        analyses: list[PlantAnalysis] = []
        for raw_item in reversed(raw_items):
            try:
                analyses.append(PlantAnalysis.from_dict(raw_item))
            except InvalidAnalysisError:
                continue
            if limit is not None and len(analyses) >= max(0, limit):
                break
        return analyses

    async def async_get_latest_analysis(self, plant_id: str) -> PlantAnalysis | None:
        """Return the newest valid analysis for a plant."""
        analyses = await self.async_get_analyses(plant_id, limit=1)
        return analyses[0] if analyses else None

    async def async_store_analysis(
        self,
        plant_id: str,
        analysis: PlantAnalysis,
    ) -> None:
        """Append a validated analysis and retain a bounded history."""
        async with self._lock:
            data = await self.async_load()
            history = data["analyses"].setdefault(plant_id, [])
            if not isinstance(history, list):
                history = []
            history.append(analysis.to_dict())
            data["analyses"][plant_id] = history[-MAX_AI_ANALYSES_PER_PLANT:]
            await self.async_save()
