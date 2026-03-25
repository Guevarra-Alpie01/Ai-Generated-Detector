from __future__ import annotations

from django.conf import settings

from detector.services.providers.base import ProviderResult
from detector.services.scoring import DetectionOutcome, clamp_score, label_from_probability


DISPLAY_NAMES = {
    "local": "local analysis",
    "illuminarty": "Illuminarty",
    "reality_defender": "Reality Defender",
}


def _display_name(provider_name: str) -> str:
    return DISPLAY_NAMES.get(provider_name, provider_name.replace("_", " ").title())


def _join_names(provider_names: list[str]) -> str:
    names = [_display_name(name) for name in provider_names]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


class ScoreAggregator:
    def combine(
        self,
        provider_results: list[ProviderResult],
        *,
        source_metadata: dict | None = None,
        local_breakdown: dict | None = None,
    ) -> DetectionOutcome:
        source_metadata = dict(source_metadata or {})
        local_breakdown = dict(local_breakdown or {})
        successful = [result for result in provider_results if result.status == "success" and result.ai_score is not None]
        skipped = [result for result in provider_results if result.status == "skipped"]
        failed = [result for result in provider_results if result.status == "failed"]

        provider_scores: dict[str, float] = {}
        weights_used: dict[str, float] = {}
        weighted_total = 0.0
        total_weight = 0.0

        for result in successful:
            weight = float(settings.DETECTION_PROVIDER_WEIGHTS.get(result.provider, 1.0))
            if weight <= 0:
                continue
            provider_scores[result.provider] = result.ai_score or 0.0
            weights_used[result.provider] = weight
            weighted_total += (result.ai_score or 0.0) * weight
            total_weight += weight

        if total_weight <= 0:
            if provider_scores:
                combined_score = sum(provider_scores.values()) / len(provider_scores)
            else:
                combined_score = 0.5
        else:
            combined_score = weighted_total / total_weight

        combined_score = clamp_score(combined_score)
        label, confidence = label_from_probability(combined_score)
        low_threshold = settings.DETECTION_LABEL_THRESHOLDS.get("low", 0.35)
        high_threshold = settings.DETECTION_LABEL_THRESHOLDS.get("high", 0.68)
        score_spread = (
            max(provider_scores.values()) - min(provider_scores.values())
            if len(provider_scores) > 1
            else 0.0
        )
        disagreement = len(provider_scores) > 1 and score_spread >= settings.DETECTION_DISAGREEMENT_SPREAD_THRESHOLD
        if disagreement and low_threshold < combined_score < high_threshold:
            label = "Uncertain"
            confidence = clamp_score(min(confidence, 1 - (score_spread / 2)))

        signals: list[str] = []
        for result in successful:
            signals.extend(result.signals[:3])
        if disagreement:
            signals.append("The successful providers disagreed on the likelihood of AI generation.")
        final_signals = list(dict.fromkeys(signals))

        providers_used = [result.provider for result in successful]
        fallback_used = "local" in providers_used
        details = self._build_details(providers_used, skipped, failed, disagreement)

        breakdown = {
            "ai_score": combined_score,
            "provider_scores": {key: round(value, 4) for key, value in provider_scores.items()},
            "provider_weights_used": weights_used,
            "provider_spread": round(score_spread, 4),
            "local": local_breakdown,
            "providers": {
                result.provider: {
                    "status": result.status,
                    "label": result.label,
                    "confidence": result.confidence,
                }
                for result in provider_results
            },
        }
        if "audio_analysis_used" in local_breakdown:
            breakdown["audio_analysis_used"] = local_breakdown["audio_analysis_used"]
        if "audio_summary" in local_breakdown:
            breakdown["audio_summary"] = local_breakdown["audio_summary"]

        provider_summary = {
            "providers": {
                result.provider: result.as_normalized_dict()
                for result in provider_results
            },
            "successful": providers_used,
            "skipped": [result.provider for result in skipped],
            "failed": [result.provider for result in failed],
            "combined_score": combined_score,
            "provider_spread": round(score_spread, 4),
        }

        raw_provider_results = {result.provider: result.raw for result in provider_results}

        return DetectionOutcome(
            label=label,
            confidence=confidence,
            details=details,
            breakdown=breakdown,
            source_metadata=source_metadata,
            signals=final_signals,
            providers_used=providers_used,
            fallback_used=fallback_used,
            provider_summary=provider_summary,
            raw_provider_results=raw_provider_results,
        )

    def _build_details(
        self,
        providers_used: list[str],
        skipped: list[ProviderResult],
        failed: list[ProviderResult],
        disagreement: bool,
    ) -> str:
        parts: list[str] = []
        external_used = [provider for provider in providers_used if provider != "local"]

        if providers_used == ["local"]:
            parts.append("Used local fallback analysis only.")
        elif "local" in providers_used and external_used:
            if len(external_used) == 1:
                parts.append(f"Combined local analysis with {_display_name(external_used[0])} result.")
            else:
                parts.append(f"Combined local analysis with {_join_names(external_used)} results.")
        elif providers_used:
            parts.append(f"Combined {_join_names(providers_used)} results.")
        else:
            parts.append("No provider returned a usable score, so the result stayed uncertain.")

        if skipped:
            skipped_names = [result.provider for result in skipped]
            verb = "was" if len(skipped_names) == 1 else "were"
            parts.append(f"{_join_names(skipped_names)} {verb} skipped.")

        if failed:
            failed_names = [result.provider for result in failed]
            parts.append(f"{_join_names(failed_names)} failed, but the local fallback remained available.")

        if disagreement:
            parts.append("The providers disagreed enough to keep the final label in the uncertain range.")

        return " ".join(parts)
