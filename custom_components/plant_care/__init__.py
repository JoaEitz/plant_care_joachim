from __future__ import annotations

import asyncio
import logging
import shutil
from functools import partial
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    SOURCE_USER,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
)
from homeassistant.data_entry_flow import (
    FlowResultType,
)
from homeassistant.exceptions import (
    HomeAssistantError,
)
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_change,
)
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    PLATFORMS,
    DEFAULT_OPTIONS,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    OPT_WATERING_INTERVAL_DAYS,
    OPT_FERTILIZING_INTERVAL_DAYS,
    OPT_MOISTURE_MIN,
    OPT_MOISTURE_MAX,
    OPT_HUMIDITY_MIN,
    OPT_HUMIDITY_MAX,
    OPT_TEMP_MIN,
    OPT_TEMP_MAX,
    OPT_LIGHT_MIN,
    OPT_LIGHT_MAX,
    OPT_TEMP_ENTITY_ID,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_MOISTURE_ENTITY_ID,
)
from .coordinator import PlantCareCoordinator
from .storage import PlantCareStorage


_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = cv.config_entry_only_config_schema(
    DOMAIN
)


SERVICE_CREATE_PLANT = "create_plant"

CONF_IMAGE_MEDIA_CONTENT_ID = (
    "image_media_content_id"
)

CONF_AREA_NAME = (
    "area_name"
)


CREATE_PLANT_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_PLANT_NAME
        ): cv.string,

        vol.Optional(
            CONF_IMAGE_MEDIA_CONTENT_ID
        ): cv.string,

        vol.Optional(
            CONF_AREA_NAME
        ): cv.string,

        vol.Optional(
            OPT_WATERING_INTERVAL_DAYS,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_WATERING_INTERVAL_DAYS
                ]
            ),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0),
        ),

        vol.Optional(
            OPT_FERTILIZING_INTERVAL_DAYS,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_FERTILIZING_INTERVAL_DAYS
                ]
            ),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0),
        ),

        vol.Optional(
            OPT_MOISTURE_MIN,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_MOISTURE_MIN
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_MOISTURE_MAX,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_MOISTURE_MAX
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_HUMIDITY_MIN,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_HUMIDITY_MIN
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_HUMIDITY_MAX,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_HUMIDITY_MAX
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_TEMP_MIN,
            default=float(
                DEFAULT_OPTIONS[
                    OPT_TEMP_MIN
                ]
            ),
        ): vol.Coerce(float),

        vol.Optional(
            OPT_TEMP_MAX,
            default=float(
                DEFAULT_OPTIONS[
                    OPT_TEMP_MAX
                ]
            ),
        ): vol.Coerce(float),

        vol.Optional(
            OPT_LIGHT_MIN,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_LIGHT_MIN
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_LIGHT_MAX,
            default=int(
                DEFAULT_OPTIONS[
                    OPT_LIGHT_MAX
                ]
            ),
        ): vol.Coerce(int),

        vol.Optional(
            OPT_TEMP_ENTITY_ID
        ): cv.string,

        vol.Optional(
            OPT_HUMIDITY_ENTITY_ID
        ): cv.string,

        vol.Optional(
            OPT_MOISTURE_ENTITY_ID
        ): cv.string,
    }
)


# ============================================================
# UNIQUE PLANT ID
# ============================================================

def _existing_plant_ids(
    hass: HomeAssistant,
) -> set[str]:
    """Return all Plant Care IDs currently in use."""

    existing_ids: set[str] = set()

    for entry in hass.config_entries.async_entries(
        DOMAIN
    ):

        plant_id = str(
            entry.data.get(
                CONF_PLANT_ID,
                "",
            )
            or ""
        ).strip()

        if plant_id:
            existing_ids.add(
                plant_id
            )

        unique_id = str(
            entry.unique_id
            or ""
        ).strip()

        if unique_id:
            existing_ids.add(
                unique_id
            )

    return existing_ids


def _generate_unique_plant_id(
    hass: HomeAssistant,
    plant_name: str,
) -> str:
    """Create the next available stable plant ID."""

    base_id = (
        slugify(
            plant_name
        )
        or "plant"
    )

    existing_ids = (
        _existing_plant_ids(
            hass
        )
    )

    if base_id not in existing_ids:
        return base_id

    index = 2

    while True:

        candidate = (
            f"{base_id}_{index}"
        )

        if candidate not in existing_ids:
            return candidate

        index += 1


# ============================================================
# ENTITY ID NORMALIZATION
# ============================================================

async def _normalize_entity_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Force Plant Care entity IDs to follow their unique IDs.

    Example:

    unique_id:
        peace_lily_2_watering_due

    entity_id:
        binary_sensor.peace_lily_2_watering_due

    This prevents Home Assistant from producing IDs such as:
        binary_sensor.peace_lily_watering_due_2
    """

    registry = er.async_get(
        hass
    )

    plant_id = str(
        entry.data.get(
            CONF_PLANT_ID,
            "",
        )
        or entry.unique_id
        or ""
    ).strip()

    if not plant_id:
        return

    # Give forwarded platforms a short moment to register
    # their entities before inspecting the registry.
    for _ in range(50):

        entries = er.async_entries_for_config_entry(
            registry,
            entry.entry_id,
        )

        if entries:
            break

        await asyncio.sleep(
            0.1
        )

    entries = er.async_entries_for_config_entry(
        registry,
        entry.entry_id,
    )

    if not entries:

        _LOGGER.warning(
            "No entity registry entries found for Plant Care '%s'",
            plant_id,
        )

        return

    changed = 0

    for entity_entry in entries:

        unique_id = str(
            entity_entry.unique_id
            or ""
        ).strip()

        if not unique_id:
            continue

        # Only touch entities belonging to this plant.
        if not unique_id.startswith(
            f"{plant_id}_"
        ):
            continue

        domain = entity_entry.entity_id.split(
            ".",
            1,
        )[0]

        desired_entity_id = (
            f"{domain}.{unique_id}"
        )

        if (
            entity_entry.entity_id
            ==
            desired_entity_id
        ):
            continue

        existing_target = (
            registry.async_get(
                desired_entity_id
            )
        )

        if (
            existing_target is not None
            and
            existing_target.id
            != entity_entry.id
        ):

            _LOGGER.error(
                "Cannot normalize Plant Care entity '%s' "
                "to '%s' because target already exists",
                entity_entry.entity_id,
                desired_entity_id,
            )

            continue

        old_entity_id = (
            entity_entry.entity_id
        )

        try:

            registry.async_update_entity(
                old_entity_id,
                new_entity_id=desired_entity_id,
            )

            changed += 1

            _LOGGER.info(
                "Normalized Plant Care entity: %s -> %s",
                old_entity_id,
                desired_entity_id,
            )

        except Exception as err:

            _LOGGER.error(
                "Failed to normalize Plant Care entity "
                "'%s' to '%s': %s",
                old_entity_id,
                desired_entity_id,
                err,
            )

    if changed:

        _LOGGER.info(
            "Normalized %s entity IDs for plant '%s'",
            changed,
            plant_id,
        )


# ============================================================
# LOCAL MEDIA
# ============================================================

def _get_local_media_directory(
    hass: HomeAssistant,
) -> Path:

    media_dirs = (
        hass.config.media_dirs
    )

    local = media_dirs.get(
        "local"
    )

    if local:
        return Path(
            local
        )

    if media_dirs:
        return Path(
            next(
                iter(
                    media_dirs.values()
                )
            )
        )

    return Path(
        "/media"
    )


def _media_content_id_to_path(
    hass: HomeAssistant,
    media_content_id: str,
) -> Path | None:

    prefix = (
        "media-source://"
        "media_source/local/"
    )

    if not media_content_id.startswith(
        prefix
    ):
        return None

    relative = (
        media_content_id[
            len(prefix):
        ]
        .lstrip("/")
    )

    if (
        not relative
        or ".." in Path(
            relative
        ).parts
    ):
        return None

    return (
        _get_local_media_directory(
            hass
        )
        / relative
    )


async def _copy_plant_image(
    hass: HomeAssistant,
    plant_id: str,
    media_content_id: str,
) -> None:

    if not media_content_id:
        return

    source = (
        _media_content_id_to_path(
            hass,
            media_content_id,
        )
    )

    if source is None:

        _LOGGER.warning(
            "Unsupported plant image media source: %s",
            media_content_id,
        )

        return

    source_exists = (
        await hass.async_add_executor_job(
            source.exists
        )
    )

    if not source_exists:

        _LOGGER.warning(
            "Plant image does not exist: %s",
            source,
        )

        return

    target_directory = Path(
        hass.config.path(
            "www",
            "plants",
        )
    )

    await hass.async_add_executor_job(
        partial(
            target_directory.mkdir,
            parents=True,
            exist_ok=True,
        )
    )

    filename = (
        plant_id.replace(
            "_",
            "-",
        )
        + ".jpg"
    )

    target = (
        target_directory
        / filename
    )

    await hass.async_add_executor_job(
        shutil.copyfile,
        source,
        target,
    )

    _LOGGER.info(
        "Plant image saved: %s",
        target,
    )


# ============================================================
# AREA
# ============================================================

def _normalize_area_name(
    value: str,
) -> str:

    cleaned = (
        value.strip()
    )

    aliases = {
        "livingroom":
            "Living Room",

        "living room":
            "Living Room",

        "office jojo":
            "Office Jojo",

        "balcony":
            "Balcony",
    }

    return aliases.get(
        cleaned.casefold(),
        cleaned,
    )


async def _assign_area(
    hass: HomeAssistant,
    entry: ConfigEntry,
    area_name: str,
) -> None:

    if not area_name:
        return

    area_name = (
        _normalize_area_name(
            area_name
        )
    )

    area_registry = (
        ar.async_get(
            hass
        )
    )

    area = (
        area_registry.async_get_area_by_name(
            area_name
        )
    )

    if area is None:

        for candidate in (
            area_registry.async_list_areas()
        ):

            if (
                candidate.name.casefold()
                ==
                area_name.casefold()
            ):

                area = candidate
                break

    if area is None:

        _LOGGER.warning(
            "Plant area '%s' does not exist",
            area_name,
        )

        return

    device_registry = (
        dr.async_get(
            hass
        )
    )

    for _ in range(100):

        for device in (
            device_registry.devices.values()
        ):

            owned_by_entry = (
                getattr(
                    device,
                    "config_entry_id",
                    None,
                )
                ==
                entry.entry_id
            )

            legacy_entries = (
                getattr(
                    device,
                    "config_entries",
                    set(),
                )
                or set()
            )

            if (
                owned_by_entry
                or
                entry.entry_id
                in legacy_entries
            ):

                device_registry.async_update_device(
                    device.id,
                    area_id=area.id,
                )

                _LOGGER.info(
                    "Assigned Plant Care device '%s' to area '%s'",
                    device.id,
                    area.name,
                )

                return

        await asyncio.sleep(
            0.1
        )

    _LOGGER.warning(
        "Could not find Plant Care device for entry %s",
        entry.entry_id,
    )


# ============================================================
# ENTITY WAIT
# ============================================================

async def _wait_for_plant_entity(
    hass: HomeAssistant,
    plant_id: str,
) -> bool:

    entity_id = (
        f"binary_sensor."
        f"{plant_id}"
        f"_watering_due"
    )

    for _ in range(100):

        if (
            hass.states.get(
                entity_id
            )
            is not None
        ):
            return True

        await asyncio.sleep(
            0.1
        )

    return False


# ============================================================
# MAIN SETUP + CREATE SERVICE
# ============================================================

async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:

    async def async_create_plant(
        call: ServiceCall,
    ) -> None:

        plant_name = str(
            call.data[
                CONF_PLANT_NAME
            ]
        ).strip()

        if not plant_name:

            raise HomeAssistantError(
                "Plant name cannot be empty."
            )

        expected_plant_id = (
            _generate_unique_plant_id(
                hass,
                plant_name,
            )
        )

        _LOGGER.info(
            "AI plant create requested: "
            "name='%s', expected_plant_id='%s'",
            plant_name,
            expected_plant_id,
        )

        area_name = str(
            call.data.get(
                CONF_AREA_NAME,
                "",
            )
            or ""
        ).strip()

        image_media_content_id = str(
            call.data.get(
                CONF_IMAGE_MEDIA_CONTENT_ID,
                "",
            )
            or ""
        ).strip()

        user_input = {
            CONF_PLANT_NAME:
                plant_name,

            OPT_WATERING_INTERVAL_DAYS:
                int(
                    call.data[
                        OPT_WATERING_INTERVAL_DAYS
                    ]
                ),

            OPT_FERTILIZING_INTERVAL_DAYS:
                int(
                    call.data[
                        OPT_FERTILIZING_INTERVAL_DAYS
                    ]
                ),

            OPT_MOISTURE_MIN:
                int(
                    call.data[
                        OPT_MOISTURE_MIN
                    ]
                ),

            OPT_MOISTURE_MAX:
                int(
                    call.data[
                        OPT_MOISTURE_MAX
                    ]
                ),

            OPT_HUMIDITY_MIN:
                int(
                    call.data[
                        OPT_HUMIDITY_MIN
                    ]
                ),

            OPT_HUMIDITY_MAX:
                int(
                    call.data[
                        OPT_HUMIDITY_MAX
                    ]
                ),

            OPT_TEMP_MIN:
                float(
                    call.data[
                        OPT_TEMP_MIN
                    ]
                ),

            OPT_TEMP_MAX:
                float(
                    call.data[
                        OPT_TEMP_MAX
                    ]
                ),

            OPT_LIGHT_MIN:
                int(
                    call.data[
                        OPT_LIGHT_MIN
                    ]
                ),

            OPT_LIGHT_MAX:
                int(
                    call.data[
                        OPT_LIGHT_MAX
                    ]
                ),
        }

        for key in (
            OPT_TEMP_ENTITY_ID,
            OPT_HUMIDITY_ENTITY_ID,
            OPT_MOISTURE_ENTITY_ID,
        ):

            value = str(
                call.data.get(
                    key,
                    "",
                )
                or ""
            ).strip()

            if value:

                user_input[
                    key
                ] = value

        # ------------------------------------------------------
        # VALIDATION
        # ------------------------------------------------------

        if (
            user_input[
                OPT_MOISTURE_MIN
            ]
            >
            user_input[
                OPT_MOISTURE_MAX
            ]
        ):

            raise HomeAssistantError(
                "Minimum soil moisture cannot be greater than maximum."
            )

        if (
            user_input[
                OPT_HUMIDITY_MIN
            ]
            >
            user_input[
                OPT_HUMIDITY_MAX
            ]
        ):

            raise HomeAssistantError(
                "Minimum humidity cannot be greater than maximum."
            )

        if (
            user_input[
                OPT_TEMP_MIN
            ]
            >
            user_input[
                OPT_TEMP_MAX
            ]
        ):

            raise HomeAssistantError(
                "Minimum temperature cannot be greater than maximum."
            )

        if (
            user_input[
                OPT_LIGHT_MIN
            ]
            >
            user_input[
                OPT_LIGHT_MAX
            ]
        ):

            raise HomeAssistantError(
                "Minimum light cannot be greater than maximum."
            )

        # ------------------------------------------------------
        # CONFIG FLOW
        # ------------------------------------------------------

        init_result = (
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={
                    "source":
                        SOURCE_USER,
                },
            )
        )

        if (
            init_result.get(
                "type"
            )
            is not FlowResultType.FORM
        ):

            raise HomeAssistantError(
                "Plant Care did not return its user configuration form."
            )

        flow_id = (
            init_result.get(
                "flow_id"
            )
        )

        if not flow_id:

            raise HomeAssistantError(
                "Plant Care config flow returned no flow ID."
            )

        result = (
            await hass.config_entries.flow.async_configure(
                flow_id,
                user_input,
            )
        )

        result_type = (
            result.get(
                "type"
            )
        )

        if (
            result_type
            is FlowResultType.CREATE_ENTRY
        ):

            entry = (
                result.get(
                    "result"
                )
            )

            if entry is None:

                raise HomeAssistantError(
                    "Plant Care returned no config entry."
                )

            returned_plant_id = str(
                entry.data.get(
                    CONF_PLANT_ID,
                    "",
                )
                or
                entry.unique_id
                or
                ""
            ).strip()

            _LOGGER.info(
                "Config flow created plant: "
                "name='%s', returned_plant_id='%s', "
                "expected_plant_id='%s', unique_id='%s'",
                plant_name,
                returned_plant_id,
                expected_plant_id,
                entry.unique_id,
            )

            data = dict(
                entry.data
            )

            data[
                CONF_PLANT_NAME
            ] = plant_name

            data[
                CONF_PLANT_ID
            ] = expected_plant_id

            if (
                returned_plant_id
                != expected_plant_id
                or
                entry.unique_id
                != expected_plant_id
            ):

                _LOGGER.warning(
                    "Correcting Plant Care entry ID "
                    "from plant_id='%s', unique_id='%s' "
                    "to '%s'",
                    returned_plant_id,
                    entry.unique_id,
                    expected_plant_id,
                )

                hass.config_entries.async_update_entry(
                    entry,
                    data=data,
                    unique_id=expected_plant_id,
                )

                await asyncio.sleep(
                    0
                )

                try:

                    await hass.config_entries.async_reload(
                        entry.entry_id
                    )

                except Exception as err:

                    _LOGGER.warning(
                        "Could not immediately reload corrected "
                        "Plant Care entry '%s': %s",
                        entry.entry_id,
                        err,
                    )

            plant_id = (
                expected_plant_id
            )

            # Give platforms time to register entities.
            await asyncio.sleep(
                0.5
            )

            # --------------------------------------------------
            # FORCE ENTITY IDS
            # --------------------------------------------------

            await _normalize_entity_ids(
                hass,
                entry,
            )

            # --------------------------------------------------
            # IMAGE
            # --------------------------------------------------

            if image_media_content_id:

                await _copy_plant_image(
                    hass,
                    plant_id,
                    image_media_content_id,
                )

            # --------------------------------------------------
            # WAIT FOR FINAL ENTITY ID
            # --------------------------------------------------

            entity_ready = (
                await _wait_for_plant_entity(
                    hass,
                    plant_id,
                )
            )

            if not entity_ready:

                _LOGGER.warning(
                    "Plant '%s' was created but "
                    "binary_sensor.%s_watering_due "
                    "was not ready after 10 seconds",
                    plant_id,
                    plant_id,
                )

            # --------------------------------------------------
            # AREA
            # --------------------------------------------------

            if area_name:

                await _assign_area(
                    hass,
                    entry,
                    area_name,
                )

            return

        if (
            result_type
            is FlowResultType.FORM
        ):

            raise HomeAssistantError(
                "Plant Care rejected the supplied values. "
                f"Errors: {result.get('errors', {})}"
            )

        if (
            result_type
            is FlowResultType.ABORT
        ):

            raise HomeAssistantError(
                "Plant creation was aborted: "
                f"{result.get('reason', 'unknown')}"
            )

        raise HomeAssistantError(
            "Unexpected Plant Care config flow result: "
            f"{result_type}"
        )

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_CREATE_PLANT,
    ):

        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_PLANT,
            async_create_plant,
            schema=CREATE_PLANT_SCHEMA,
        )

    return True


# ============================================================
# CONFIG ENTRY SETUP
# ============================================================

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:

    hass.data.setdefault(
        DOMAIN,
        {},
    )

    hass.data[
        DOMAIN
    ].setdefault(
        "storage",
        PlantCareStorage(
            hass
        ),
    )

    storage: PlantCareStorage = (
        hass.data[
            DOMAIN
        ][
            "storage"
        ]
    )

    if hasattr(
        storage,
        "async_setup",
    ):

        await storage.async_setup()

    if not entry.options:

        init_opts = dict(
            DEFAULT_OPTIONS
        )

        for key in DEFAULT_OPTIONS:

            if key in entry.data:

                init_opts[
                    key
                ] = entry.data[
                    key
                ]

        hass.config_entries.async_update_entry(
            entry,
            options=init_opts,
        )

    coordinator = (
        PlantCareCoordinator(
            hass,
            entry,
            storage,
        )
    )

    hass.data[
        DOMAIN
    ][
        entry.entry_id
    ] = {
        "coordinator":
            coordinator,

        "storage":
            storage,
    }

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    # ----------------------------------------------------------
    # NORMALIZE EXISTING ENTITIES TOO
    #
    # This is important: an already-created Peace Lily #2 can
    # be repaired automatically on restart.
    # ----------------------------------------------------------

    await _normalize_entity_ids(
        hass,
        entry,
    )

    unsub_listener = (
        coordinator.async_add_listener(
            lambda: None
        )
    )

    entry.async_on_unload(
        unsub_listener
    )

    await coordinator.async_config_entry_first_refresh()

    async def _delayed_refresh(
        _now,
    ) -> None:

        await coordinator.async_refresh()

    entry.async_on_unload(
        async_call_later(
            hass,
            60,
            _delayed_refresh,
        )
    )

    async def _daily_refresh(
        _now,
    ) -> None:

        await coordinator.async_refresh()

    unsub_daily = (
        async_track_time_change(
            hass,
            _daily_refresh,
            hour=3,
            minute=0,
            second=0,
        )
    )

    entry.async_on_unload(
        unsub_daily
    )

    return True


# ============================================================
# UNLOAD
# ============================================================

async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:

    unload_ok = (
        await hass.config_entries.async_unload_platforms(
            entry,
            PLATFORMS,
        )
    )

    if unload_ok:

        hass.data[
            DOMAIN
        ].pop(
            entry.entry_id,
            None,
        )

    return unload_ok