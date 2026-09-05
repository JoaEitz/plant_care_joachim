"""Errors raised by the AI plant-health subsystem."""

from homeassistant.exceptions import HomeAssistantError


class PlantAnalysisError(HomeAssistantError):
    """Base error for a plant analysis failure."""


class AIConfigurationError(PlantAnalysisError):
    """The AI provider configuration is incomplete or invalid."""


class ImageResolutionError(PlantAnalysisError):
    """The configured image could not be resolved or validated."""


class InvalidAnalysisError(PlantAnalysisError):
    """The provider returned an invalid structured response."""


class ProviderAuthenticationError(PlantAnalysisError):
    """The AI provider rejected its credentials."""


class ProviderRateLimitError(PlantAnalysisError):
    """The AI provider rate or quota limit was reached."""


class ProviderRequestError(PlantAnalysisError):
    """The AI provider request failed."""
