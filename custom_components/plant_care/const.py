from __future__ import annotations

DOMAIN = "plant_care"

PLATFORMS = ["sensor", "binary_sensor", "button", "number"]

# Entry data keys
CONF_PLANT_ID = "plant_id"
CONF_PLANT_NAME = "plant_name"

# Task types
TASK_WATERING = "watering"
TASK_FERTILIZING = "fertilizing"
TASKS = (TASK_WATERING, TASK_FERTILIZING)

# Option keys (stored in config_entry.options)
OPT_WATERING_INTERVAL_DAYS = "watering_interval_days"
OPT_FERTILIZING_INTERVAL_DAYS = "fertilizing_interval_days"

OPT_MOISTURE_MIN = "moisture_min"
OPT_MOISTURE_MAX = "moisture_max"

OPT_HUMIDITY_MIN = "humidity_min"
OPT_HUMIDITY_MAX = "humidity_max"

OPT_TEMP_MIN = "temp_min"
OPT_TEMP_MAX = "temp_max"

OPT_LIGHT_MIN = "light_min"
OPT_LIGHT_MAX = "light_max"

# Optional external source sensors (entity_ids)
OPT_TEMP_ENTITY_ID = "temp_entity_id"
OPT_HUMIDITY_ENTITY_ID = "humidity_entity_id"
OPT_MOISTURE_ENTITY_ID = "moisture_entity_id"
OPT_LIGHT_ENTITY_ID = "light_entity_id"
OPT_CONDUCTIVITY_ENTITY_ID = "conductivity_entity_id"

# Optional plant metadata
OPT_PLANT_SPECIES = "plant_species"

# AI health analysis options
OPT_AI_ENABLED = "ai_enabled"
OPT_AI_PROVIDER = "ai_provider"
OPT_AI_API_KEY = "ai_api_key"
OPT_AI_MODEL = "ai_model"
OPT_AI_HISTORY_DAYS = "ai_history_days"
OPT_AI_PREVIOUS_ANALYSIS_LIMIT = "ai_previous_analysis_limit"
OPT_AI_IMAGE_ENTITY_ID = "ai_image_entity_id"
OPT_AI_IMAGE_MEDIA_CONTENT_ID = "ai_image_media_content_id"

AI_PROVIDER_OPENAI = "openai"
DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_HISTORY_DAYS = 14
DEFAULT_AI_PREVIOUS_ANALYSIS_LIMIT = 3
MAX_AI_ANALYSES_PER_PLANT = 20
MAX_AI_IMAGE_BYTES = 10 * 1024 * 1024

# Mixed-type defaults: numbers + strings
# (Intervals support 0 to disable; entity_id empty string means "not configured")
DEFAULT_OPTIONS: dict[str, bool | float | str] = {
    OPT_WATERING_INTERVAL_DAYS: 7,
    OPT_FERTILIZING_INTERVAL_DAYS: 30,
    OPT_MOISTURE_MIN: 0,
    OPT_MOISTURE_MAX: 100,
    OPT_HUMIDITY_MIN: 0,
    OPT_HUMIDITY_MAX: 100,
    OPT_TEMP_MIN: 10,
    OPT_TEMP_MAX: 30,
    OPT_LIGHT_MIN: 0,
    OPT_LIGHT_MAX: 100000,
    OPT_TEMP_ENTITY_ID: "",
    OPT_HUMIDITY_ENTITY_ID: "",
    OPT_MOISTURE_ENTITY_ID: "",
    OPT_LIGHT_ENTITY_ID: "",
    OPT_CONDUCTIVITY_ENTITY_ID: "",
    OPT_PLANT_SPECIES: "",
    OPT_AI_ENABLED: False,
    OPT_AI_PROVIDER: AI_PROVIDER_OPENAI,
    OPT_AI_API_KEY: "",
    OPT_AI_MODEL: DEFAULT_AI_MODEL,
    OPT_AI_HISTORY_DAYS: DEFAULT_AI_HISTORY_DAYS,
    OPT_AI_PREVIOUS_ANALYSIS_LIMIT: DEFAULT_AI_PREVIOUS_ANALYSIS_LIMIT,
    OPT_AI_IMAGE_ENTITY_ID: "",
    OPT_AI_IMAGE_MEDIA_CONTENT_ID: "",
}

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 2
STORAGE_KEY = f"{DOMAIN}_state"


def plant_object_id(entry, suffix: str) -> str:
    plant_id = entry.data.get(CONF_PLANT_ID, entry.entry_id)
    return f"{plant_id}_{suffix}"
