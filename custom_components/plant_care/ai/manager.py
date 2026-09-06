"""Orchestrate one on-demand plant-health analysis."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import (
    AI_PROVIDER_HOME_ASSISTANT,
    AI_PROVIDER_OPENAI,
    CONF_PLANT_ID,
    DEFAULT_OPTIONS,
    OPT_AI_API_KEY,
    OPT_AI_ENABLED,
    OPT_AI_MODEL,
    OPT_AI_PROVIDER,
    OPT_AI_TASK_ENTITY_ID,
)
from ..coordinator import PlantCareCoordinator
from ..image import PlantImageResolver
from ..storage import PlantCareStorage
from .context import PlantContextBuilder
from .errors import AIConfigurationError, PlantAnalysisError
from .home_assistant import HomeAssistantAITaskPlantAIProvider
from .models import PlantAnalysis
from .openai import OpenAIPlantAIProvider
from .provider import PlantAIProvider

ProviderFactory = Callable[[], PlantAIProvider]


class PlantAnalysisManager:
    """Resolve inputs, call a provider, persist, and publish one result."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: PlantCareCoordinator,
        storage: PlantCareStorage,
        *,
        context_builder: PlantContextBuilder | None = None,
        image_resolver: PlantImageResolver | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._storage = storage
        self._context_builder = context_builder or PlantContextBuilder(
            hass, entry, coordinator, storage
        )
        self._image_resolver = image_resolver or PlantImageResolver(hass, entry)
        self._provider_factory = provider_factory
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def async_analyze(
        self,
        *,
        image_entity_id: str | None = None,
        media_content_id: str | None = None,
        image_path: str | None = None,
    ) -> PlantAnalysis:
        """Run a complete analysis for this manager's plant."""
        if self._lock.locked():
            raise PlantAnalysisError("An AI analysis is already running for this plant")
        async with self._lock:
            self._ensure_available()
            if not bool(
                self._entry.options.get(OPT_AI_ENABLED, DEFAULT_OPTIONS[OPT_AI_ENABLED])
            ):
                raise AIConfigurationError(
                    "AI health analysis is disabled for this plant"
                )

            provider = self._create_provider()
            image = await self._image_resolver.async_resolve(
                image_entity_id=image_entity_id,
                media_content_id=media_content_id,
                image_path=image_path,
            )
            context = await self._context_builder.async_build()
            self._ensure_available()
            analysis = await provider.async_analyze(
                image.content,
                image.mime_type,
                context,
            )

            self._ensure_available()
            plant_id = str(self._entry.data.get(CONF_PLANT_ID, self._entry.entry_id))
            await self._storage.async_store_analysis(plant_id, analysis)
            await self._coordinator.async_refresh()
            return analysis

    def _create_provider(self) -> PlantAIProvider:
        if self._provider_factory is not None:
            return self._provider_factory()

        provider_name = str(
            self._entry.options.get(OPT_AI_PROVIDER, DEFAULT_OPTIONS[OPT_AI_PROVIDER])
        ).strip()
        if provider_name == AI_PROVIDER_HOME_ASSISTANT:
            entity_id = str(
                self._entry.options.get(OPT_AI_TASK_ENTITY_ID, "") or ""
            ).strip()
            if entity_id and not entity_id.startswith("ai_task."):
                raise AIConfigurationError(
                    "The configured Home Assistant AI Task entity is invalid"
                )
            return HomeAssistantAITaskPlantAIProvider(
                self._hass,
                entity_id or None,
            )

        if provider_name != AI_PROVIDER_OPENAI:
            raise AIConfigurationError(
                f"Unsupported AI provider: {provider_name or 'empty'}"
            )

        api_key = str(self._entry.options.get(OPT_AI_API_KEY, "") or "").strip()
        if not api_key:
            raise AIConfigurationError(
                "OpenAI API key is missing from this plant's options"
            )
        model = str(
            self._entry.options.get(OPT_AI_MODEL, DEFAULT_OPTIONS[OPT_AI_MODEL]) or ""
        ).strip()
        if not model:
            raise AIConfigurationError("OpenAI model cannot be empty")

        return OpenAIPlantAIProvider(
            async_get_clientsession(self._hass),
            api_key,
            model,
        )

    def _ensure_available(self) -> None:
        state_value = getattr(self._hass.state, "value", str(self._hass.state)).lower()
        if state_value in {"stopping", "stopped"}:
            raise PlantAnalysisError(
                "Home Assistant is shutting down; analysis was cancelled"
            )
        current_entry = self._hass.config_entries.async_get_entry(self._entry.entry_id)
        if current_entry is None:
            raise PlantAnalysisError("The plant was removed during analysis")
