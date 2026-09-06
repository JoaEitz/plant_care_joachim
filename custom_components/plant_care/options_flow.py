from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    AI_PROVIDER_HOME_ASSISTANT,
    AI_PROVIDER_OPENAI,
    DEFAULT_OPTIONS,
    OPT_AI_API_KEY,
    OPT_AI_ENABLED,
    OPT_AI_HISTORY_DAYS,
    OPT_AI_IMAGE_ENTITY_ID,
    OPT_AI_IMAGE_MEDIA_CONTENT_ID,
    OPT_AI_MODEL,
    OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
    OPT_AI_PROVIDER,
    OPT_AI_TASK_ENTITY_ID,
    OPT_CONDUCTIVITY_ENTITY_ID,
    OPT_HUMIDITY_ENTITY_ID,
    OPT_LIGHT_ENTITY_ID,
    OPT_MOISTURE_ENTITY_ID,
    OPT_PLANT_SPECIES,
    OPT_TEMP_ENTITY_ID,
)


class PlantCareOptionsFlowHandler(config_entries.OptionsFlow):
    """Configure source sensors and AI analysis for one plant."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            new_options = dict(self._config_entry.options)
            for key in (
                OPT_TEMP_ENTITY_ID,
                OPT_HUMIDITY_ENTITY_ID,
                OPT_MOISTURE_ENTITY_ID,
                OPT_LIGHT_ENTITY_ID,
                OPT_CONDUCTIVITY_ENTITY_ID,
                OPT_AI_IMAGE_ENTITY_ID,
                OPT_AI_IMAGE_MEDIA_CONTENT_ID,
                OPT_AI_TASK_ENTITY_ID,
                OPT_PLANT_SPECIES,
                OPT_AI_API_KEY,
                OPT_AI_MODEL,
                OPT_AI_PROVIDER,
            ):
                new_options[key] = str(user_input.get(key) or "").strip()

            new_options[OPT_AI_ENABLED] = bool(user_input[OPT_AI_ENABLED])
            new_options[OPT_AI_HISTORY_DAYS] = int(user_input[OPT_AI_HISTORY_DAYS])
            new_options[OPT_AI_PREVIOUS_ANALYSIS_LIMIT] = int(
                user_input[OPT_AI_PREVIOUS_ANALYSIS_LIMIT]
            )

            if (
                new_options[OPT_AI_ENABLED]
                and new_options[OPT_AI_PROVIDER] == AI_PROVIDER_OPENAI
                and not new_options[OPT_AI_API_KEY]
            ):
                errors["base"] = "missing_api_key"
            else:
                return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    def _build_schema(self, user_input):
        current = dict(self._config_entry.options)
        if user_input:
            current.update(user_input)

        def optional_text(key: str, *, password: bool = False):
            value = str(current.get(key, DEFAULT_OPTIONS.get(key, "")) or "")
            marker = vol.Optional(key, default=value) if value else vol.Optional(key)
            text_type = "password" if password else "text"
            return marker, selector.TextSelector(
                selector.TextSelectorConfig(type=text_type)
            )

        def optional_entity(key: str, domains: str | list[str] = "sensor"):
            value = str(current.get(key, "") or "").strip()
            marker = vol.Optional(key, default=value) if value else vol.Optional(key)
            return marker, selector.EntitySelector(
                selector.EntitySelectorConfig(domain=domains)
            )

        species_key, species_selector = optional_text(OPT_PLANT_SPECIES)
        api_key, api_selector = optional_text(OPT_AI_API_KEY, password=True)
        model_key, model_selector = optional_text(OPT_AI_MODEL)
        media_key, media_selector = optional_text(OPT_AI_IMAGE_MEDIA_CONTENT_ID)

        fields: dict = {species_key: species_selector}
        for key in (
            OPT_TEMP_ENTITY_ID,
            OPT_HUMIDITY_ENTITY_ID,
            OPT_MOISTURE_ENTITY_ID,
            OPT_LIGHT_ENTITY_ID,
            OPT_CONDUCTIVITY_ENTITY_ID,
        ):
            marker, entity_selector = optional_entity(key)
            fields[marker] = entity_selector

        image_marker, image_selector = optional_entity(
            OPT_AI_IMAGE_ENTITY_ID, ["camera", "image"]
        )
        ai_task_marker, ai_task_selector = optional_entity(
            OPT_AI_TASK_ENTITY_ID, "ai_task"
        )
        fields.update(
            {
                vol.Required(
                    OPT_AI_ENABLED,
                    default=bool(
                        current.get(OPT_AI_ENABLED, DEFAULT_OPTIONS[OPT_AI_ENABLED])
                    ),
                ): selector.BooleanSelector(),
                vol.Required(
                    OPT_AI_PROVIDER,
                    default=str(
                        current.get(OPT_AI_PROVIDER, DEFAULT_OPTIONS[OPT_AI_PROVIDER])
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": AI_PROVIDER_HOME_ASSISTANT,
                                "label": "Home Assistant AI Task (Gemini)",
                            },
                            {
                                "value": AI_PROVIDER_OPENAI,
                                "label": "OpenAI (direct)",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                ai_task_marker: ai_task_selector,
                api_key: api_selector,
                model_key: model_selector,
                vol.Required(
                    OPT_AI_HISTORY_DAYS,
                    default=int(
                        current.get(
                            OPT_AI_HISTORY_DAYS,
                            DEFAULT_OPTIONS[OPT_AI_HISTORY_DAYS],
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                vol.Required(
                    OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
                    default=int(
                        current.get(
                            OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
                            DEFAULT_OPTIONS[OPT_AI_PREVIOUS_ANALYSIS_LIMIT],
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                image_marker: image_selector,
                media_key: media_selector,
            }
        )
        return vol.Schema(fields)
