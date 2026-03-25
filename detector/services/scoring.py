from dataclasses import dataclass, field

from django.conf import settings


def clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Total detection weight must be greater than zero.")

    weighted_total = 0.0
    for key, weight in weights.items():
        weighted_total += clamp_score(scores.get(key, 0.5)) * weight
    return clamp_score(weighted_total / total_weight)


def label_from_probability(ai_probability: float, threshold: float | None = None) -> tuple[str, float]:
    threshold = threshold if threshold is not None else settings.AI_DETECTION_LABEL_THRESHOLD
    ai_probability = clamp_score(ai_probability)
    if ai_probability >= threshold:
        return "AI-generated", round(ai_probability * 100, 2)
    return "Likely real", round((1 - ai_probability) * 100, 2)


@dataclass(slots=True)
class DetectionOutcome:
    label: str
    confidence: float
    details: str
    breakdown: dict[str, float | str | list[str]]
    source_metadata: dict[str, str | float | int | list[str] | dict]


@dataclass(slots=True)
class ComponentAssessment:
    model_score: float = 0.5
    metadata_score: float = 0.25
    artifact_score: float = 0.25
    frame_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, float | list[str]]:
        return {
            "model_score": clamp_score(self.model_score),
            "metadata_score": clamp_score(self.metadata_score),
            "artifact_score": clamp_score(self.artifact_score),
            "frame_score": clamp_score(self.frame_score),
            "notes": self.notes,
        }
