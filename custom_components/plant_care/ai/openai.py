"""OpenAI implementation of the plant-health provider interface."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from aiohttp import ClientError, ClientSession
from homeassistant.util import dt as dt_util

from .errors import (
    InvalidAnalysisError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRequestError,
)
from .models import PlantAnalysis, PlantAnalysisContext
from .prompt import PLANT_ANALYSIS_SCHEMA, SYSTEM_PROMPT
from .provider import PlantAIProvider

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 60


class OpenAIPlantAIProvider(PlantAIProvider):
    """Analyze plants with OpenAI's multimodal Responses API."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        model: str,
        *,
        endpoint: str = OPENAI_RESPONSES_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._model = model
        self._endpoint = endpoint

    async def async_analyze(
        self,
        image: bytes,
        image_mime_type: str,
        plant_context: PlantAnalysisContext,
    ) -> PlantAnalysis:
        encoded_image = base64.b64encode(image).decode("ascii")
        payload = {
            "model": self._model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this plant using the following JSON context:\n"
                                + json.dumps(
                                    plant_context.to_dict(),
                                    separators=(",", ":"),
                                    ensure_ascii=False,
                                )
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": (
                                f"data:{image_mime_type};base64,{encoded_image}"
                            ),
                            "detail": "high",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "plant_health_analysis",
                    "description": "Validated plant health and care advice",
                    "strict": True,
                    "schema": PLANT_ANALYSIS_SCHEMA,
                }
            },
            "max_output_tokens": 1200,
            "store": False,
        }

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    response_status = response.status
                    try:
                        response_data = await response.json(content_type=None)
                    except (ValueError, TypeError) as err:
                        raise ProviderRequestError(
                            "OpenAI returned a non-JSON response"
                        ) from err
        except TimeoutError as err:
            raise ProviderRequestError("OpenAI request timed out") from err
        except ClientError as err:
            raise ProviderRequestError(
                f"OpenAI request failed: {type(err).__name__}"
            ) from err

        if response_status in (401, 403):
            raise ProviderAuthenticationError("OpenAI rejected the configured API key")
        if response_status == 429:
            raise ProviderRateLimitError(
                "OpenAI rate or quota limit was reached; try again later"
            )
        if response_status >= 400:
            error_code = _response_error_code(response_data)
            suffix = f" ({error_code})" if error_code else ""
            raise ProviderRequestError(
                f"OpenAI returned HTTP {response_status}{suffix}"
            )

        return parse_openai_response(response_data)


def _response_error_code(response_data: Any) -> str | None:
    if not isinstance(response_data, dict):
        return None
    error = response_data.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return str(code)[:80] if code else None


def parse_openai_response(response_data: Any) -> PlantAnalysis:
    """Extract and validate structured output from an OpenAI response."""
    if not isinstance(response_data, dict):
        raise InvalidAnalysisError("OpenAI response must be an object")

    output_text = response_data.get("output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        output_text = None
        output = response_data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "refusal":
                        raise InvalidAnalysisError(
                            "OpenAI declined to analyze the supplied image"
                        )
                    if part.get("type") == "output_text" and isinstance(
                        part.get("text"), str
                    ):
                        output_text = part["text"]
                        break
                if output_text:
                    break

    if not output_text:
        raise InvalidAnalysisError("OpenAI response contained no structured output")

    try:
        parsed = json.loads(output_text)
    except (TypeError, json.JSONDecodeError) as err:
        raise InvalidAnalysisError("OpenAI returned malformed JSON") from err

    return PlantAnalysis.from_ai_dict(parsed, analyzed_at=dt_util.utcnow())
