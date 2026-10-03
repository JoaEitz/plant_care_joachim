"""Home Assistant services for plant-health analysis."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from ..const import CONF_PLANT_ID, DOMAIN
from ..service_helpers import (
    PLANT_TARGET_SCHEMA,
    resolve_plant_entry,
)

SERVICE_ANALYZE_PLANT = "analyze_plant"
SERVICE_GET_ANALYSIS_HISTORY = "get_analysis_history"
CONF_IMAGE_ENTITY = "image_entity"
CONF_IMAGE_MEDIA_CONTENT_ID = "image_media_content_id"
CONF_IMAGE_PATH = "image_path"
CONF_LIMIT = "limit"

ANALYZE_PLANT_SCHEMA = vol.Schema(
    {
        **PLANT_TARGET_SCHEMA,
        vol.Optional(CONF_IMAGE_ENTITY): cv.entity_id,
        vol.Optional(CONF_IMAGE_MEDIA_CONTENT_ID): cv.string,
        vol.Optional(CONF_IMAGE_PATH): cv.string,
    }
)

GET_ANALYSIS_HISTORY_SCHEMA = vol.Schema(
    {
        **PLANT_TARGET_SCHEMA,
        vol.Optional(CONF_LIMIT, default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
    }
)


def async_register_ai_services(hass: HomeAssistant) -> None:
    """Register domain-level services once."""

    async def async_analyze_plant(call: ServiceCall) -> dict[str, Any]:
        entry = resolve_plant_entry(hass, call.data)
        runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
        manager = runtime.get("analysis_manager")
        if manager is None:
            raise HomeAssistantError("The selected Plant Care entry is not loaded")
        analysis = await manager.async_analyze(
            image_entity_id=call.data.get(CONF_IMAGE_ENTITY),
            media_content_id=call.data.get(CONF_IMAGE_MEDIA_CONTENT_ID),
            image_path=call.data.get(CONF_IMAGE_PATH),
        )
        return analysis.to_dict()

    async def async_get_analysis_history(call: ServiceCall) -> dict[str, Any]:
        entry = resolve_plant_entry(hass, call.data)
        runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
        storage = runtime.get("storage")
        if storage is None:
            raise HomeAssistantError("The selected Plant Care entry is not loaded")
        plant_id = str(entry.data.get(CONF_PLANT_ID, entry.entry_id))
        analyses = await storage.async_get_analyses(
            plant_id,
            limit=int(call.data[CONF_LIMIT]),
        )
        return {
            "plant_id": plant_id,
            "analyses": [analysis.to_dict() for analysis in analyses],
        }

    if not hass.services.has_service(DOMAIN, SERVICE_ANALYZE_PLANT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ANALYZE_PLANT,
            async_analyze_plant,
            schema=ANALYZE_PLANT_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_ANALYSIS_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_ANALYSIS_HISTORY,
            async_get_analysis_history,
            schema=GET_ANALYSIS_HISTORY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
