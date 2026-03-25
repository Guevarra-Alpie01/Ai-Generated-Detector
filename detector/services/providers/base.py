from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from detector.services.scoring import clamp_score, label_from_probability
from detector.utils.temp_files import sanitize_json_payload


@dataclass(slots=True)
class ProviderResult:
    provider: str
    label: str
    confidence: float
    signals: list[str] = field(default_factory=list)
    raw: dict | list | str | int | float | bool | None = field(default_factory=dict)
    status: str = "success"
    ai_score: float | None = None
    details: str = ""

    @classmethod
    def success(
        cls,
        provider: str,
        *,
        ai_score: float,
        signals: list[str] | None = None,
        raw: Any = None,
        details: str = "",
    ) -> "ProviderResult":
        label, confidence = label_from_probability(ai_score)
        return cls(
            provider=provider,
            label=label,
            confidence=confidence,
            signals=list(dict.fromkeys(signals or [])),
            raw=sanitize_json_payload(raw or {}),
            status="success",
            ai_score=clamp_score(ai_score),
            details=details,
        )

    @classmethod
    def skipped(
        cls,
        provider: str,
        reason: str,
        *,
        raw: Any = None,
        signals: list[str] | None = None,
    ) -> "ProviderResult":
        return cls(
            provider=provider,
            label="Uncertain",
            confidence=0.0,
            signals=list(dict.fromkeys((signals or []) + [reason])),
            raw=sanitize_json_payload(raw or {"reason": reason}),
            status="skipped",
            ai_score=None,
            details=reason,
        )

    @classmethod
    def failed(
        cls,
        provider: str,
        reason: str,
        *,
        raw: Any = None,
        signals: list[str] | None = None,
    ) -> "ProviderResult":
        return cls(
            provider=provider,
            label="Uncertain",
            confidence=0.0,
            signals=list(dict.fromkeys((signals or []) + [reason])),
            raw=sanitize_json_payload(raw or {"reason": reason}),
            status="failed",
            ai_score=None,
            details=reason,
        )

    def as_normalized_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "label": self.label,
            "confidence": self.confidence,
            "signals": self.signals,
            "raw": self.raw,
            "status": self.status,
        }


class BaseDetectionProvider:
    provider_name = ""

    def skipped(self, reason: str, *, raw: Any = None, signals: list[str] | None = None) -> ProviderResult:
        return ProviderResult.skipped(self.provider_name, reason, raw=raw, signals=signals)

    def failed(self, reason: str, *, raw: Any = None, signals: list[str] | None = None) -> ProviderResult:
        return ProviderResult.failed(self.provider_name, reason, raw=raw, signals=signals)

    def success(
        self,
        *,
        ai_score: float,
        signals: list[str] | None = None,
        raw: Any = None,
        details: str = "",
    ) -> ProviderResult:
        return ProviderResult.success(
            self.provider_name,
            ai_score=ai_score,
            signals=signals,
            raw=raw,
            details=details,
        )
