"""Home Assistant services for plant-health analysis."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from ..const import CONF_PLANT_ID, DOMAIN

SERVICE_ANALYZE_PLANT = "analyze_plant"
SERVICE_GET_ANALYSIS_HISTORY = "get_analysis_history"
CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_IMAGE_ENTITY = "image_entity"
CONF_IMAGE_MEDIA_CONTENT_ID = "image_media_content_id"
CONF_IMAGE_PATH = "image_path"
CONF_LIMIT = "limit"

PLANT_TARGET_SCHEMA = {
    vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(CONF_PLANT_ID): cv.string,
}

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
        entry = _resolve_entry(hass, call.data)
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
        entry = _resolve_entry(hass, call.data)
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


def _resolve_entry(hass: HomeAssistant, data: dict[str, Any]) -> ConfigEntry:
    entry_id = str(data.get(CONF_CONFIG_ENTRY_ID, "") or "").strip()
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry
        raise HomeAssistantError("No Plant Care entry matches config_entry_id")

    plant_id = str(data.get(CONF_PLANT_ID, "") or "").strip()
    if plant_id:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if plant_id in {
                str(entry.data.get(CONF_PLANT_ID, "") or ""),
                str(entry.unique_id or ""),
            }:
                return entry
        raise HomeAssistantError("No Plant Care entry matches plant_id")

    device_value = data.get(ATTR_DEVICE_ID)
    if isinstance(device_value, list):
        if len(device_value) != 1:
            raise HomeAssistantError("Target exactly one Plant Care device")
        device_value = device_value[0]
    device_id = str(device_value or "").strip()
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise HomeAssistantError("The selected device does not exist")
        config_entry_ids = getattr(device, "config_entries", set()) or set()
        legacy_entry_id = getattr(device, "config_entry_id", None)
        if legacy_entry_id:
            config_entry_ids = set(config_entry_ids) | {legacy_entry_id}
        for candidate_id in config_entry_ids:
            entry = hass.config_entries.async_get_entry(candidate_id)
            if entry is not None and entry.domain == DOMAIN:
                return entry
        raise HomeAssistantError("The selected device is not a Plant Care device")

    raise HomeAssistantError(
        "Target a Plant Care device or provide config_entry_id or plant_id"
    )
