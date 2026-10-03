"""Shared helpers for Plant Care service targets."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import CONF_PLANT_ID, DOMAIN

CONF_CONFIG_ENTRY_ID = "config_entry_id"

PLANT_TARGET_SCHEMA = {
    vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(CONF_PLANT_ID): cv.string,
}


def resolve_plant_entry(hass: HomeAssistant, data: dict[str, Any]) -> ConfigEntry:
    """Resolve exactly one Plant Care config entry from service data."""
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
