"""Typed models for plant-health context and results."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .errors import InvalidAnalysisError

HEALTH_STATUSES = ("healthy", "watch", "stressed", "critical", "unknown")
URGENCY_LEVELS = ("low", "medium", "high", "urgent")
WATERING_RECOMMENDATIONS = ("water", "wait", "monitor", "check", "reduce")


def _required_string(
    value: Any,
    field_name: str,
    *,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise InvalidAnalysisError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned and not allow_empty:
        raise InvalidAnalysisError(f"{field_name} cannot be empty")
    if len(cleaned) > max_length:
        raise InvalidAnalysisError(f"{field_name} is too long")
    return cleaned


def _required_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAnalysisError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidAnalysisError(f"{field_name} must be finite")
    return number


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidAnalysisError(f"{field_name} must be a list")
    if len(value) > 10:
        raise InvalidAnalysisError(f"{field_name} has too many items")
    return tuple(
        _required_string(item, f"{field_name} item", max_length=500) for item in value
    )


@dataclass(frozen=True, slots=True)
class PlantWateringAdvice:
    """Structured watering advice returned by a provider."""

    recommendation: str
    reason: str

    @classmethod
    def from_dict(cls, data: Any) -> PlantWateringAdvice:
        if not isinstance(data, dict):
            raise InvalidAnalysisError("watering must be an object or null")
        if set(data) - {"recommendation", "reason"}:
            raise InvalidAnalysisError("watering contains unexpected fields")
        recommendation = _required_string(
            data.get("recommendation"),
            "watering.recommendation",
            max_length=32,
        ).lower()
        if recommendation not in WATERING_RECOMMENDATIONS:
            raise InvalidAnalysisError("watering.recommendation is invalid")
        return cls(
            recommendation=recommendation,
            reason=_required_string(
                data.get("reason"),
                "watering.reason",
                max_length=1000,
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "recommendation": self.recommendation,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PlantAnalysis:
    """Validated plant-health result persisted by the integration."""

    health_score: int
    status: str
    attention_required: bool
    confidence: float
    primary_issue: str | None
    summary: str
    observations: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    urgency: str
    watering: PlantWateringAdvice | None
    analyzed_at: datetime

    @classmethod
    def from_ai_dict(
        cls,
        data: Any,
        *,
        analyzed_at: datetime,
    ) -> PlantAnalysis:
        """Validate provider output and add the locally controlled timestamp."""
        if not isinstance(data, dict):
            raise InvalidAnalysisError("AI response must be a JSON object")
        allowed_fields = {
            "health_score",
            "status",
            "attention_required",
            "confidence",
            "primary_issue",
            "summary",
            "observations",
            "recommended_actions",
            "urgency",
            "watering",
        }
        if set(data) - allowed_fields:
            raise InvalidAnalysisError("AI response contains unexpected fields")

        score_number = _required_number(data.get("health_score"), "health_score")
        if not score_number.is_integer() or not 0 <= score_number <= 100:
            raise InvalidAnalysisError("health_score must be an integer from 0 to 100")

        confidence = _required_number(data.get("confidence"), "confidence")
        if not 0 <= confidence <= 1:
            raise InvalidAnalysisError("confidence must be between 0 and 1")

        attention_required = data.get("attention_required")
        if not isinstance(attention_required, bool):
            raise InvalidAnalysisError("attention_required must be a boolean")

        status = _required_string(data.get("status"), "status", max_length=32).lower()
        if status not in HEALTH_STATUSES:
            raise InvalidAnalysisError("status is invalid")

        urgency = _required_string(
            data.get("urgency"), "urgency", max_length=32
        ).lower()
        if urgency not in URGENCY_LEVELS:
            raise InvalidAnalysisError("urgency is invalid")

        primary_issue_value = data.get("primary_issue")
        primary_issue = None
        if primary_issue_value is not None:
            primary_issue = _required_string(
                primary_issue_value,
                "primary_issue",
                max_length=255,
            )

        watering_value = data.get("watering")
        watering = (
            PlantWateringAdvice.from_dict(watering_value)
            if watering_value is not None
            else None
        )

        if analyzed_at.tzinfo is None:
            raise InvalidAnalysisError("analyzed_at must be timezone-aware")

        return cls(
            health_score=int(score_number),
            status=status,
            attention_required=attention_required,
            confidence=confidence,
            primary_issue=primary_issue,
            summary=_required_string(data.get("summary"), "summary", max_length=2000),
            observations=_string_list(data.get("observations"), "observations"),
            recommended_actions=_string_list(
                data.get("recommended_actions"), "recommended_actions"
            ),
            urgency=urgency,
            watering=watering,
            analyzed_at=analyzed_at,
        )

    @classmethod
    def from_dict(cls, data: Any) -> PlantAnalysis:
        """Validate a stored analysis."""
        if not isinstance(data, dict):
            raise InvalidAnalysisError("Stored analysis must be an object")
        analyzed_at_value = data.get("analyzed_at")
        if not isinstance(analyzed_at_value, str):
            raise InvalidAnalysisError("analyzed_at must be an ISO datetime")
        analyzed_at = dt_util.parse_datetime(analyzed_at_value)
        if analyzed_at is None:
            raise InvalidAnalysisError("analyzed_at must be an ISO datetime")
        analysis_data = dict(data)
        analysis_data.pop("analyzed_at")
        return cls.from_ai_dict(analysis_data, analyzed_at=analyzed_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": self.health_score,
            "status": self.status,
            "attention_required": self.attention_required,
            "confidence": self.confidence,
            "primary_issue": self.primary_issue,
            "summary": self.summary,
            "observations": list(self.observations),
            "recommended_actions": list(self.recommended_actions),
            "urgency": self.urgency,
            "watering": self.watering.to_dict() if self.watering else None,
            "analyzed_at": self.analyzed_at.isoformat(),
        }

    def to_compact_context(self) -> dict[str, Any]:
        """Return the small subset useful as context for a later analysis."""
        result: dict[str, Any] = {
            "analyzed_at": self.analyzed_at.date().isoformat(),
            "health_score": self.health_score,
            "status": self.status,
            "attention_required": self.attention_required,
        }
        if self.primary_issue:
            result["primary_issue"] = self.primary_issue
        return result


@dataclass(frozen=True, slots=True)
class DailyMeasurement:
    date: str
    average: float

    def to_dict(self) -> dict[str, str | float]:
        return {"date": self.date, "average": self.average}


@dataclass(frozen=True, slots=True)
class HistoricalMeasurement:
    current: float | None
    minimum: float
    maximum: float
    average: float
    start: float
    end: float
    change: float
    trend: str
    samples: int
    daily: tuple[DailyMeasurement, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "min": self.minimum,
            "max": self.maximum,
            "average": self.average,
            "start": self.start,
            "end": self.end,
            "change": self.change,
            "trend": self.trend,
            "samples": self.samples,
        }
        if self.current is not None:
            result["current"] = self.current
        if self.daily:
            result["daily"] = [item.to_dict() for item in self.daily]
        return result


@dataclass(frozen=True, slots=True)
class PlantAnalysisContext:
    """Structured measured and configured context supplied to a provider."""

    plant: dict[str, Any]
    current: dict[str, Any]
    care: dict[str, Any]
    history: dict[str, HistoricalMeasurement]
    previous_ai_analyses: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"plant": self.plant}
        if self.current:
            result["current"] = self.current
        if self.care:
            result["care"] = self.care
        if self.history:
            result["history"] = {
                metric: measurement.to_dict()
                for metric, measurement in self.history.items()
            }
        if self.previous_ai_analyses:
            result["previous_ai_analyses"] = list(self.previous_ai_analyses)
        return result
