"""Provider-independent interface for plant-health analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import PlantAnalysis, PlantAnalysisContext


class PlantAIProvider(ABC):
    """Analyze a plant image and structured Home Assistant context."""

    @abstractmethod
    async def async_analyze(
        self,
        image: bytes,
        image_mime_type: str,
        plant_context: PlantAnalysisContext,
    ) -> PlantAnalysis:
        """Return one validated plant-health analysis."""
