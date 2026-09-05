from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    AI_PROVIDER_OPENAI,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_AI_API_KEY,
    OPT_AI_ENABLED,
    OPT_AI_HISTORY_DAYS,
    OPT_AI_MODEL,
    OPT_AI_PREVIOUS_ANALYSIS_LIMIT,
    OPT_AI_PROVIDER,
)
from custom_components.plant_care.options_flow import PlantCareOptionsFlowHandler


def ai_input(api_key: str):
    return {
        OPT_AI_ENABLED: True,
        OPT_AI_PROVIDER: AI_PROVIDER_OPENAI,
        OPT_AI_API_KEY: api_key,
        OPT_AI_MODEL: "gpt-4o-mini",
        OPT_AI_HISTORY_DAYS: 14,
        OPT_AI_PREVIOUS_ANALYSIS_LIMIT: 3,
    }


async def test_options_flow_requires_key_when_ai_is_enabled():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=dict(DEFAULT_OPTIONS),
    )
    flow = PlantCareOptionsFlowHandler(entry)

    result = await flow.async_step_init(ai_input(""))

    assert result["type"] == "form"
    assert result["errors"] == {"base": "missing_api_key"}


async def test_options_flow_saves_ai_configuration():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=dict(DEFAULT_OPTIONS),
    )
    flow = PlantCareOptionsFlowHandler(entry)

    result = await flow.async_step_init(ai_input("secret-key"))

    assert result["type"] == "create_entry"
    assert result["data"][OPT_AI_ENABLED] is True
    assert result["data"][OPT_AI_API_KEY] == "secret-key"
