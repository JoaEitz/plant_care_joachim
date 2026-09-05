"""Resolve and validate plant images without blocking Home Assistant's event loop."""

from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .ai.errors import ImageResolutionError
from .const import (
    CONF_PLANT_ID,
    MAX_AI_IMAGE_BYTES,
    OPT_AI_IMAGE_ENTITY_ID,
    OPT_AI_IMAGE_MEDIA_CONTENT_ID,
)

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
LOCAL_MEDIA_PREFIX = "media-source://media_source/local/"


@dataclass(frozen=True, slots=True)
class ResolvedPlantImage:
    content: bytes
    mime_type: str


def get_local_media_directory(hass: HomeAssistant) -> Path:
    media_dirs = hass.config.media_dirs
    if local := media_dirs.get("local"):
        return Path(local)
    if media_dirs:
        return Path(next(iter(media_dirs.values())))
    return Path("/media")


def media_content_id_to_path(
    hass: HomeAssistant,
    media_content_id: str,
) -> Path | None:
    if not media_content_id.startswith(LOCAL_MEDIA_PREFIX):
        return None
    relative = media_content_id[len(LOCAL_MEDIA_PREFIX) :].lstrip("/")
    if not relative or ".." in Path(relative).parts:
        return None
    return get_local_media_directory(hass) / relative


def default_plant_image_path(hass: HomeAssistant, plant_id: str) -> Path:
    filename = plant_id.replace("_", "-") + ".jpg"
    return Path(hass.config.path("www", "plants", filename))


async def async_copy_plant_image(
    hass: HomeAssistant,
    plant_id: str,
    media_content_id: str,
) -> None:
    """Copy a local media image into the existing Plant Care image location."""
    source = media_content_id_to_path(hass, media_content_id)
    if source is None:
        raise ImageResolutionError(
            "Only local Home Assistant media images are supported"
        )
    if not await hass.async_add_executor_job(source.is_file):
        raise ImageResolutionError("The selected local media image does not exist")

    target = default_plant_image_path(hass, plant_id)
    await hass.async_add_executor_job(
        partial(target.parent.mkdir, parents=True, exist_ok=True)
    )
    await hass.async_add_executor_job(shutil.copyfile, source, target)


class PlantImageResolver:
    """Resolve a camera, image entity, local media item, or allowlisted file."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    async def async_resolve(
        self,
        *,
        image_entity_id: str | None = None,
        media_content_id: str | None = None,
        image_path: str | None = None,
    ) -> ResolvedPlantImage:
        if image_entity_id:
            return await self._async_from_entity(image_entity_id.strip())
        if media_content_id:
            path = media_content_id_to_path(self._hass, media_content_id.strip())
            if path is None:
                raise ImageResolutionError(
                    "The configured media ID is not a local Home Assistant image"
                )
            return await self._async_from_path(path)
        if image_path:
            path = Path(image_path)
            if not self._hass.config.is_allowed_path(str(path)):
                raise ImageResolutionError(
                    "The image path is not allowlisted in Home Assistant"
                )
            return await self._async_from_path(path)

        configured_entity = str(
            self._entry.options.get(OPT_AI_IMAGE_ENTITY_ID, "") or ""
        ).strip()
        if configured_entity:
            return await self._async_from_entity(configured_entity)
        configured_media = str(
            self._entry.options.get(OPT_AI_IMAGE_MEDIA_CONTENT_ID, "") or ""
        ).strip()
        if configured_media:
            path = media_content_id_to_path(self._hass, configured_media)
            if path is None:
                raise ImageResolutionError(
                    "The configured media ID is not a local Home Assistant image"
                )
            return await self._async_from_path(path)

        plant_id = str(self._entry.data.get(CONF_PLANT_ID, self._entry.entry_id))
        fallback = default_plant_image_path(self._hass, plant_id)
        if await self._hass.async_add_executor_job(fallback.is_file):
            return await self._async_from_path(fallback)
        raise ImageResolutionError(
            "No image is configured. Set an AI image entity or local media image "
            "in the plant options, or pass one to plant_care.analyze_plant."
        )

    async def _async_from_entity(self, entity_id: str) -> ResolvedPlantImage:
        state = self._hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise ImageResolutionError(f"Image source {entity_id} is unavailable")

        domain = entity_id.partition(".")[0]
        try:
            if domain == "camera":
                from homeassistant.components.camera import async_get_image

                image = await async_get_image(
                    self._hass,
                    entity_id,
                    timeout=15,
                    width=1280,
                    height=1280,
                )
                return self._validate(image.content, image.content_type)

            if domain == "image":
                component: Any = self._hass.data.get("image")
                image_entity = component.get_entity(entity_id) if component else None
                if image_entity is None:
                    raise ImageResolutionError(
                        f"Image entity {entity_id} is not loaded"
                    )
                content = await image_entity.async_image()
                if content is None:
                    raise ImageResolutionError(
                        f"Image entity {entity_id} returned no image"
                    )
                return self._validate(content, image_entity.content_type)
        except ImageResolutionError:
            raise
        except Exception as err:
            raise ImageResolutionError(
                f"Unable to fetch image from {entity_id}: {type(err).__name__}"
            ) from err

        raise ImageResolutionError("Image source must be a camera or image entity")

    async def _async_from_path(self, path: Path) -> ResolvedPlantImage:
        if not await self._hass.async_add_executor_job(path.is_file):
            raise ImageResolutionError("The selected image file does not exist")
        size = await self._hass.async_add_executor_job(lambda: path.stat().st_size)
        if size > MAX_AI_IMAGE_BYTES:
            raise ImageResolutionError(
                f"Image exceeds the {MAX_AI_IMAGE_BYTES // (1024 * 1024)} MB limit"
            )
        try:
            content = await self._hass.async_add_executor_job(path.read_bytes)
        except OSError as err:
            raise ImageResolutionError("Unable to read the selected image") from err
        guessed_type = mimetypes.guess_type(path.name)[0]
        detected_type = _detect_image_type(content)
        return self._validate(content, detected_type or guessed_type)

    def _validate(
        self,
        content: bytes,
        declared_type: str | None,
    ) -> ResolvedPlantImage:
        if not content:
            raise ImageResolutionError("The selected image is empty")
        if len(content) > MAX_AI_IMAGE_BYTES:
            raise ImageResolutionError(
                f"Image exceeds the {MAX_AI_IMAGE_BYTES // (1024 * 1024)} MB limit"
            )

        detected_type = _detect_image_type(content)
        normalized_declared = (declared_type or "").partition(";")[0].lower().strip()
        if normalized_declared == "image/jpg":
            normalized_declared = "image/jpeg"
        mime_type = detected_type or normalized_declared
        if mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ImageResolutionError(
                "Unsupported image format; use JPEG, PNG, or WebP"
            )
        if detected_type and normalized_declared in SUPPORTED_IMAGE_TYPES:
            if detected_type != normalized_declared:
                raise ImageResolutionError("Image content does not match its MIME type")
        return ResolvedPlantImage(content=content, mime_type=mime_type)


def _detect_image_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None
