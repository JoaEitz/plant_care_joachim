from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_OPTIONS,
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


_LOGGER = logging.getLogger(__name__)


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_PLANT_NAME
        ): selector.TextSelector(),

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
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor"
            )
        ),

        vol.Optional(
            OPT_HUMIDITY_ENTITY_ID
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor"
            )
        ),

        vol.Optional(
            OPT_MOISTURE_ENTITY_ID
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor"
            )
        ),
    }
)


class PlantCareConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):

    VERSION = 1


    @staticmethod
    def async_get_options_flow(
        config_entry,
    ):

        from .options_flow import (
            PlantCareOptionsFlowHandler,
        )

        return PlantCareOptionsFlowHandler(
            config_entry
        )


    def _existing_plant_ids(
        self,
    ) -> set[str]:
        """Return every Plant Care ID already in use."""

        existing_ids: set[str] = set()

        entries = (
            self.hass.config_entries.async_entries(
                DOMAIN
            )
        )

        for entry in entries:

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

        _LOGGER.info(
            "Existing Plant Care IDs: %s",
            sorted(existing_ids),
        )

        return existing_ids


    def _generate_unique_plant_id(
        self,
        plant_name: str,
    ) -> str:
        """Generate stable unique plant ID.

        Examples:

        Peace Lily
            -> peace_lily

        second Peace Lily
            -> peace_lily_2

        third Peace Lily
            -> peace_lily_3
        """

        base_id = (
            slugify(
                plant_name
            )
            or "plant"
        )

        existing_ids = (
            self._existing_plant_ids()
        )

        if (
            base_id
            not in existing_ids
        ):

            _LOGGER.info(
                "Generated Plant Care ID '%s' for '%s'",
                base_id,
                plant_name,
            )

            return base_id

        number = 2

        while True:

            candidate = (
                f"{base_id}_{number}"
            )

            if (
                candidate
                not in existing_ids
            ):

                _LOGGER.info(
                    "Generated duplicate Plant Care ID "
                    "'%s' for '%s'",
                    candidate,
                    plant_name,
                )

                return candidate

            number += 1


    async def async_step_user(
        self,
        user_input=None,
    ) -> FlowResult:

        if user_input is None:

            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
            )

        plant_name = str(
            user_input[
                CONF_PLANT_NAME
            ]
        ).strip()

        if not plant_name:

            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
                errors={
                    CONF_PLANT_NAME:
                        "invalid_name"
                },
            )

        #######################################################################
        # GENERATE UNIQUE INTERNAL ID
        #######################################################################

        plant_id = (
            self._generate_unique_plant_id(
                plant_name
            )
        )

        #######################################################################
        # USE INTERNAL ID AS CONFIG ENTRY UNIQUE ID
        #######################################################################

        await self.async_set_unique_id(
            plant_id
        )

        self._abort_if_unique_id_configured()

        #######################################################################
        # OPTIONAL EXTERNAL SENSORS
        #######################################################################

        temp_entity = str(
            user_input.get(
                OPT_TEMP_ENTITY_ID
            )
            or ""
        ).strip()

        humidity_entity = str(
            user_input.get(
                OPT_HUMIDITY_ENTITY_ID
            )
            or ""
        ).strip()

        moisture_entity = str(
            user_input.get(
                OPT_MOISTURE_ENTITY_ID
            )
            or ""
        ).strip()

        #######################################################################
        # OPTIONS
        #######################################################################

        options = {
            OPT_WATERING_INTERVAL_DAYS:
                int(
                    user_input[
                        OPT_WATERING_INTERVAL_DAYS
                    ]
                ),

            OPT_FERTILIZING_INTERVAL_DAYS:
                int(
                    user_input[
                        OPT_FERTILIZING_INTERVAL_DAYS
                    ]
                ),

            OPT_MOISTURE_MIN:
                int(
                    user_input[
                        OPT_MOISTURE_MIN
                    ]
                ),

            OPT_MOISTURE_MAX:
                int(
                    user_input[
                        OPT_MOISTURE_MAX
                    ]
                ),

            OPT_HUMIDITY_MIN:
                int(
                    user_input[
                        OPT_HUMIDITY_MIN
                    ]
                ),

            OPT_HUMIDITY_MAX:
                int(
                    user_input[
                        OPT_HUMIDITY_MAX
                    ]
                ),

            OPT_TEMP_MIN:
                float(
                    user_input[
                        OPT_TEMP_MIN
                    ]
                ),

            OPT_TEMP_MAX:
                float(
                    user_input[
                        OPT_TEMP_MAX
                    ]
                ),

            OPT_LIGHT_MIN:
                int(
                    user_input[
                        OPT_LIGHT_MIN
                    ]
                ),

            OPT_LIGHT_MAX:
                int(
                    user_input[
                        OPT_LIGHT_MAX
                    ]
                ),

            OPT_TEMP_ENTITY_ID:
                temp_entity,

            OPT_HUMIDITY_ENTITY_ID:
                humidity_entity,

            OPT_MOISTURE_ENTITY_ID:
                moisture_entity,
        }

        #######################################################################
        # CONFIG ENTRY DATA
        #######################################################################

        data = {
            CONF_PLANT_NAME:
                plant_name,

            CONF_PLANT_ID:
                plant_id,
        }

        _LOGGER.info(
            "Creating Plant Care entry: "
            "name='%s', plant_id='%s'",
            plant_name,
            plant_id,
        )

        return self.async_create_entry(
            title=plant_name,
            data=data,
            options=options,
        )