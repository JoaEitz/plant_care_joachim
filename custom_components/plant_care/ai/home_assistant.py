"""Provider using Home Assistant's configured AI Task entity."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from ..image import LOCAL_MEDIA_PREFIX, get_local_media_directory
from .errors import (
    InvalidAnalysisError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRequestError,
)
from .models import (
    HEALTH_STATUSES,
    URGENCY_LEVELS,
    WATERING_RECOMMENDATIONS,
    PlantAnalysis,
    PlantAnalysisContext,
)
from .prompt import SYSTEM_PROMPT
from .provider import PlantAIProvider

REQUEST_TIMEOUT_SECONDS = 60
AI_TASK_DOMAIN = "ai_task"
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

AI_TASK_STRUCTURE = vol.Schema(
    {
        vol.Required(
            "health_score", description="Integer plant health score from 0 to 100"
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=100, step=1)
        ),
        vol.Required(
            "status", description="Overall plant health status"
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(HEALTH_STATUSES))
        ),
        vol.Required(
            "attention_required",
            description="Whether the plant currently needs attention",
        ): selector.BooleanSelector(),
        vol.Required(
            "confidence", description="Confidence from 0.0 to 1.0"
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=1, step=0.01)
        ),
        vol.Optional(
            "primary_issue", description="Short primary issue, or omit when none"
        ): selector.TextSelector(),
        vol.Required(
            "summary", description="Concise evidence-based plant health summary"
        ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Required(
            "observations", description="List of observations supported by the evidence"
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        vol.Required(
            "recommended_actions", description="List of practical next actions"
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        vol.Required(
            "urgency", description="Urgency of the recommended actions"
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(URGENCY_LEVELS))
        ),
        vol.Optional(
            "watering_recommendation",
            description="Watering advice; omit only when no advice is possible",
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(WATERING_RECOMMENDATIONS))
        ),
        vol.Optional(
            "watering_reason", description="Reason for the watering advice"
        ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
    },
    extra=vol.PREVENT_EXTRA,
)

AITaskRunner = Callable[..., Awaitable[Any]]


class HomeAssistantAITaskPlantAIProvider(PlantAIProvider):
    """Analyze a plant using an existing Home Assistant AI Task entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str | None,
        *,
        runner: AITaskRunner | None = None,
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id or None
        self._runner = runner

    async def async_analyze(
        self,
        image: bytes,
        image_mime_type: str,
        plant_context: PlantAnalysisContext,
    ) -> PlantAnalysis:
        """Send the image and structured context through Home Assistant AI Task."""
        runner = self._runner
        if runner is None:
            if not await async_setup_component(self._hass, AI_TASK_DOMAIN, {}):
                raise ProviderRequestError("Home Assistant AI Task could not be loaded")
            from homeassistant.components.ai_task import async_generate_data

            runner = async_generate_data

        path, media_content_id = await self._async_stage_image(image, image_mime_type)
        context_json = json.dumps(
            plant_context.to_dict(), separators=(",", ":"), ensure_ascii=False
        )
        instructions = (
            f"{SYSTEM_PROMPT}\n\n"
            "Analyze the attached current plant image using this JSON context:\n"
            f"{context_json}"
        )
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                result = await runner(
                    hass=self._hass,
                    entity_id=self._entity_id,
                    task_name="plant_care_health_analysis",
                    instructions=instructions,
                    structure=AI_TASK_STRUCTURE,
                    attachments=[{"media_content_id": media_content_id}],
                )
        except TimeoutError as err:
            raise ProviderRequestError("Home Assistant AI Task timed out") from err
        except HomeAssistantError as err:
            raise _map_ai_task_error(err) from err
        except Exception as err:
            raise ProviderRequestError(
                f"Home Assistant AI Task failed: {type(err).__name__}"
            ) from err
        finally:
            await self._hass.async_add_executor_job(path.unlink, True)

        raw_data = getattr(result, "data", result)
        if not isinstance(raw_data, dict):
            raise InvalidAnalysisError(
                "Home Assistant AI Task returned no structured data"
            )
        return PlantAnalysis.from_ai_dict(
            _normalize_ai_task_result(raw_data), analyzed_at=dt_util.utcnow()
        )

    async def _async_stage_image(
        self,
        content: bytes,
        mime_type: str,
    ) -> tuple[Path, str]:
        extension = IMAGE_EXTENSIONS.get(mime_type)
        if extension is None:
            raise ProviderRequestError("AI Task received an unsupported image type")
        relative_path = Path("plant_care_ai") / f"{uuid4().hex}{extension}"
        target = get_local_media_directory(self._hass) / relative_path

        def write_image() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        try:
            await self._hass.async_add_executor_job(write_image)
        except OSError as err:
            raise ProviderRequestError(
                "Unable to stage the image for Home Assistant AI Task"
            ) from err
        media_content_id = LOCAL_MEDIA_PREFIX + relative_path.as_posix()
        return target, media_content_id


def _normalize_ai_task_result(data: dict[str, Any]) -> dict[str, Any]:
    """Convert AI Task's flat selector result into PlantAnalysis input."""
    normalized = dict(data)
    watering_recommendation = normalized.pop("watering_recommendation", None)
    watering_reason = normalized.pop("watering_reason", None)
    if watering_recommendation is None and watering_reason is None:
        normalized["watering"] = None
    elif isinstance(watering_recommendation, str) and isinstance(watering_reason, str):
        normalized["watering"] = {
            "recommendation": watering_recommendation,
            "reason": watering_reason,
        }
    else:
        raise InvalidAnalysisError("AI Task returned incomplete watering advice")
    normalized.setdefault("primary_issue", None)
    return normalized


def _map_ai_task_error(error: HomeAssistantError) -> ProviderRequestError:
    """Map common provider errors without exposing credentials or payloads."""
    message = str(error).lower()
    if any(term in message for term in ("quota", "rate limit", "resource_exhausted")):
        return ProviderRateLimitError(
            "The configured AI Task provider reached its rate or quota limit"
        )
    if any(
        term in message
        for term in (
            "api key",
            "authentication",
            "unauthenticated",
            "permission denied",
        )
    ):
        return ProviderAuthenticationError(
            "The configured AI Task provider rejected its credentials"
        )
    return ProviderRequestError("The configured Home Assistant AI Task failed")
