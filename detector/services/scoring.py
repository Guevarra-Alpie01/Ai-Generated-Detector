from dataclasses import dataclass, field

from django.conf import settings


def clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def weighted_score(scores: dict[str, float | None], weights: dict[str, float]) -> float:
    weighted_total = 0.0
    available_weight = 0.0
    for key, weight in weights.items():
        score = scores.get(key)
        if score is None:
            continue
        weighted_total += clamp_score(score) * weight
        available_weight += weight

    if available_weight <= 0:
        return 0.5
    return clamp_score(weighted_total / available_weight)


def get_label_thresholds(thresholds: dict[str, float] | None = None) -> dict[str, float]:
    configured = thresholds or settings.DETECTION_LABEL_THRESHOLDS
    low = clamp_score(configured.get("low", 0.35))
    high = clamp_score(configured.get("high", 0.68))
    if high <= low:
        return {"low": 0.35, "high": 0.68}
    return {"low": low, "high": high}


def label_from_probability(
    ai_probability: float,
    thresholds: dict[str, float] | None = None,
) -> tuple[str, float]:
    ai_probability = clamp_score(ai_probability)
    resolved_thresholds = get_label_thresholds(thresholds)
    low = resolved_thresholds["low"]
    high = resolved_thresholds["high"]
    midpoint = (low + high) / 2
    uncertainty_band = max((high - low) / 2, 0.001)

    if ai_probability >= high:
        return "AI-generated", ai_probability
    if ai_probability <= low:
        return "Likely real", clamp_score(1 - ai_probability)

    uncertainty_confidence = 1 - abs(ai_probability - midpoint) / uncertainty_band
    return "Uncertain", clamp_score(uncertainty_confidence)


@dataclass(slots=True)
class DetectionOutcome:
    label: str
    confidence: float
    details: str
    breakdown: dict[str, float | int | str | bool | list[str] | dict | None]
    source_metadata: dict[str, str | float | int | bool | list[str] | dict]
    signals: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    fallback_used: bool = False
    provider_summary: dict[str, dict | list | str | float | bool | None] = field(default_factory=dict)
    raw_provider_results: dict[str, dict | list | str | float | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class ComponentAssessment:
    model_score: float | None = None
    metadata_score: float = 0.5
    artifact_score: float = 0.5
    frame_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    analysis_stats: dict[str, float | bool] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, float | list[str] | None]:
        return {
            "model_score": clamp_score(self.model_score) if self.model_score is not None else None,
            "metadata_score": clamp_score(self.metadata_score),
            "artifact_score": clamp_score(self.artifact_score),
            "frame_score": clamp_score(self.frame_score),
            "notes": self.notes,
        }
