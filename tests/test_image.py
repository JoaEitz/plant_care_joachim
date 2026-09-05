from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.ai.errors import ImageResolutionError
from custom_components.plant_care.const import (
    CONF_PLANT_ID,
    DOMAIN,
    MAX_AI_IMAGE_BYTES,
    OPT_AI_IMAGE_MEDIA_CONTENT_ID,
)
from custom_components.plant_care.image import PlantImageResolver


def make_entry(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PLANT_ID: "fern"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def test_local_media_image_resolution(hass, tmp_path: Path):
    hass.config.media_dirs = {"local": str(tmp_path)}
    image_path = tmp_path / "plant.png"
    await hass.async_add_executor_job(image_path.write_bytes, b"\x89PNG\r\n\x1a\nplant")
    entry = make_entry(
        hass,
        {
            OPT_AI_IMAGE_MEDIA_CONTENT_ID: (
                "media-source://media_source/local/plant.png"
            )
        },
    )

    image = await PlantImageResolver(hass, entry).async_resolve()

    assert image.mime_type == "image/png"
    assert image.content.startswith(b"\x89PNG")


async def test_missing_default_image(hass):
    resolver = PlantImageResolver(hass, make_entry(hass))
    with pytest.raises(ImageResolutionError, match="No image is configured"):
        await resolver.async_resolve()


def test_unsupported_and_oversized_images(hass):
    resolver = PlantImageResolver(hass, make_entry(hass))
    with pytest.raises(ImageResolutionError, match="Unsupported"):
        resolver._validate(b"not an image", "application/octet-stream")
    with pytest.raises(ImageResolutionError, match="10 MB"):
        resolver._validate(b"\xff\xd8\xff" + b"x" * MAX_AI_IMAGE_BYTES, "image/jpeg")
