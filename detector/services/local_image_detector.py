from __future__ import annotations

from PIL import Image
from django.conf import settings

from detector.services.providers.base import ProviderResult
from detector.services.scoring import clamp_score, label_from_probability, weighted_score
from detector.utils.image_features import analyse_image_features, prepare_working_image
from detector.utils.metadata_checks import assess_image_metadata
from detector.utils.temp_files import sanitize_json_payload
from media_handler.services.image_utils import load_preprocessed_image


class LocalImageDetector:
    provider_name = "local"

    def detect(
        self,
        image_path: str,
        external_metadata: dict | None = None,
    ) -> tuple[ProviderResult, dict, dict]:
        image, metadata = load_preprocessed_image(image_path, max_dimension=settings.MAX_IMAGE_DIMENSION)
        if external_metadata:
            metadata.update(external_metadata)
        return self.detect_pil_image(image, metadata=metadata)

    def detect_pil_image(
        self,
        image: Image.Image,
        metadata: dict | None = None,
    ) -> tuple[ProviderResult, dict, dict]:
        source_metadata = dict(metadata or {})
        working_image = prepare_working_image(image, settings.LOCAL_IMAGE_WORKING_SIZE)
        stats = analyse_image_features(working_image)
        metadata_score, metadata_signals = assess_image_metadata(source_metadata)
        artifact_score, artifact_signals = self._score_artifacts(stats)
        frequency_score, frequency_signals = self._score_frequency(stats)
        signals = [*metadata_signals, *artifact_signals, *frequency_signals]

        if self._is_preview_based_source(source_metadata):
            metadata_score, artifact_score, frequency_score, signals = self._calibrate_preview_scores(
                metadata_score,
                artifact_score,
                frequency_score,
                signals,
                source_metadata,
            )
        else:
            metadata_score, artifact_score, frequency_score, guard_signals = self._apply_consistency_guard(
                metadata_score,
                artifact_score,
                frequency_score,
                stats,
            )
            signals.extend(guard_signals)

        ai_score = weighted_score(
            {
                "metadata_score": metadata_score,
                "artifact_score": artifact_score,
                "frequency_score": frequency_score,
            },
            settings.LOCAL_IMAGE_COMPONENT_WEIGHTS,
        )
        label, confidence = label_from_probability(ai_score)
        compact_stats = {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in stats.items()
        }
        unique_signals = list(dict.fromkeys(signals))
        details = (
            "; ".join(unique_signals[:3])
            if unique_signals
            else "Local image heuristics stayed close to neutral and do not support a strong claim."
        )

        breakdown = {
            "label": label,
            "confidence": confidence,
            "ai_score": ai_score,
            "metadata_score": round(metadata_score, 4),
            "artifact_score": round(artifact_score, 4),
            "frequency_score": round(frequency_score, 4),
            "analysis_stats": compact_stats,
            "signals": unique_signals,
        }
        source_metadata["analysis_stats"] = compact_stats

        raw_payload = sanitize_json_payload(
            {
                "metadata_score": round(metadata_score, 4),
                "artifact_score": round(artifact_score, 4),
                "frequency_score": round(frequency_score, 4),
                "analysis_stats": compact_stats,
                "source_metadata": {
                    key: value
                    for key, value in source_metadata.items()
                    if key != "analysis_stats"
                },
            }
        )

        result = ProviderResult(
            provider=self.provider_name,
            label=label,
            confidence=confidence,
            signals=unique_signals,
            raw=raw_payload,
            status="success",
            ai_score=ai_score,
            details=details,
        )
        return result, source_metadata, breakdown

    def _is_preview_based_source(self, metadata: dict) -> bool:
        return bool(metadata.get("preview_strategy") or metadata.get("provider") in {"youtube", "facebook"})

    def _calibrate_preview_scores(
        self,
        metadata_score: float,
        artifact_score: float,
        frequency_score: float,
        signals: list[str],
        metadata: dict,
    ) -> tuple[float, float, float, list[str]]:
        provider = str(metadata.get("provider", "")).lower()
        preserved_signals = [
            signal
            for signal in signals
            if "Metadata references" in signal or "Camera acquisition metadata" in signal
        ]
        preview_signals = [
            "This result is based on a platform preview image rather than the original media.",
            "Thumbnail compression can imitate AI-like artifacts, so preview evidence is weighted conservatively.",
        ]
        if provider == "youtube":
            preview_signals[1] = (
                "YouTube thumbnails often use aggressive edits and compression, so preview evidence is weighted conservatively."
            )

        return (
            clamp_score(0.5 + (metadata_score - 0.5) * 0.2),
            clamp_score(0.44 + (artifact_score - 0.5) * 0.2),
            clamp_score(0.46 + (frequency_score - 0.5) * 0.18),
            list(dict.fromkeys([*preserved_signals, *preview_signals])),
        )

    def _score_artifacts(self, stats: dict) -> tuple[float, list[str]]:
        ai_evidence = 0.0
        real_evidence = 0.0
        signals: list[str] = []
        clip_total = stats["shadow_clip"] + stats["highlight_clip"]

        if (
            stats["edge_density"] < 0.016
            and stats["local_noise"] < 0.004
            and stats["detail_residual"] < 0.01
        ):
            if clip_total < 0.004 and stats["saturation"] < 0.28 and 7.1 <= stats["entropy"] <= 7.8:
                real_evidence += 0.22
                signals.append("Texture is smooth, but the tonal roll-off and restrained colors still look photographic.")
            else:
                ai_evidence += 0.22
                signals.append("Textures look unusually smooth, which can happen when generative models suppress natural noise.")
        elif (
            stats["edge_density"] > 0.026
            and stats["detail_residual"] > 0.0065
            and stats["saturation_spread"] > 0.2
            and stats["local_noise"] < 0.0058
        ):
            ai_evidence += 0.18
            signals.append(
                "Edges and micro-contrast are elevated while fine noise stays unusually clean, which is common in synthetic renders."
            )
        elif (
            0.01 <= stats["edge_density"] <= 0.05
            and stats["detail_residual"] <= 0.006
            and stats["saturation_spread"] < 0.16
        ):
            real_evidence += 0.14
            signals.append("Edge strength and texture detail stay within a camera-like range.")

        if (
            stats["edge_density"] > 0.02
            and stats["local_noise"] > 0.0045
            and stats["high_frequency_ratio"] > 0.2
            and stats["frequency_direction_bias"] < 0.2
            and clip_total < 0.04
        ):
            real_evidence += 0.18
            signals.append(
                "Fine-grain detail and noise vary naturally, which is more consistent with a real camera photo than a rendered image."
            )

        if clip_total > 0.025:
            ai_evidence += 0.16
            signals.append("Shadows and highlights clip aggressively, which is more common in rendered or heavily synthesized media.")
        elif clip_total < 0.004:
            real_evidence += 0.12
            signals.append("The tonal histogram avoids harsh clipping, which supports a natural capture.")

        if (
            stats["saturation_spread"] > 0.2
            and stats["contrast"] >= 0.2
            and (clip_total > 0.02 or stats["local_noise"] < 0.0045)
        ):
            ai_evidence += 0.08
            signals.append("Color variation is unusually wide for the observed contrast, hinting at synthetic color transitions.")
        elif stats["saturation_spread"] < 0.14 and stats["saturation"] < 0.26:
            real_evidence += 0.08
            signals.append("Color variation is restrained and consistent with a camera capture.")

        if stats["entropy"] > 7.6 and stats["detail_residual"] > 0.006:
            ai_evidence += 0.10
            signals.append("Very high tonal complexity paired with strong local detail can indicate generated textures.")
        elif 7.1 <= stats["entropy"] <= 7.6 and stats["detail_residual"] < 0.005 and clip_total < 0.01:
            real_evidence += 0.06

        if (
            stats["histogram_fill"] > 0.97
            and stats["saturation_histogram_fill"] > 0.95
            and clip_total > 0.02
        ):
            ai_evidence += 0.08
            signals.append(
                "The export uses almost the full tonal and saturation range, which is more common in rendered imagery than phone photos."
            )

        score = clamp_score(0.5 + ai_evidence - real_evidence)
        if not signals:
            signals.append("Artifact checks were mixed, so the local image detector stayed near neutral.")
        return score, list(dict.fromkeys(signals))

    def _score_frequency(self, stats: dict) -> tuple[float, list[str]]:
        ai_evidence = 0.0
        real_evidence = 0.0
        signals: list[str] = []

        high_ratio = stats["high_frequency_ratio"]
        mid_ratio = stats["mid_frequency_ratio"]
        low_ratio = stats["low_frequency_ratio"]
        direction_bias = stats["frequency_direction_bias"]
        spike_ratio = stats["spectral_spike_ratio"]

        if high_ratio < 0.18 and mid_ratio > 0.48 and stats["local_noise"] < 0.0045:
            ai_evidence += 0.16
            signals.append(
                "Frequency energy is concentrated in the mid band with limited natural high-frequency texture."
            )
        elif 0.18 <= high_ratio <= 0.32 and direction_bias < 0.08:
            real_evidence += 0.10
            signals.append("Frequency balance looks closer to a camera capture than a heavily synthesized render.")

        if spike_ratio > 0.004 and direction_bias > 0.08:
            ai_evidence += 0.14
            signals.append("Frequency-domain energy shows narrow spikes consistent with synthetic sharpening or tiling.")
        elif spike_ratio < 0.0025 and low_ratio > 0.05:
            real_evidence += 0.06

        if high_ratio > 0.26 and stats["noise_variation"] > 0.035 and stats["detail_variation"] > 0.025:
            real_evidence += 0.08
            signals.append("Fine detail spreads across the frequency range in a way that looks more photographic than synthetic.")
        elif high_ratio < 0.14 and stats["detail_variation"] < 0.03:
            ai_evidence += 0.08
            signals.append("High-frequency detail looks thinner than a natural capture would usually produce.")

        score = clamp_score(0.5 + ai_evidence - real_evidence)
        if not signals:
            signals.append("Frequency-domain evidence stayed close to neutral.")
        return score, list(dict.fromkeys(signals))

    def _apply_consistency_guard(
        self,
        metadata_score: float,
        artifact_score: float,
        frequency_score: float,
        stats: dict,
    ) -> tuple[float, float, float, list[str]]:
        signals: list[str] = []
        scores = {
            "metadata": metadata_score,
            "artifact": artifact_score,
            "frequency": frequency_score,
        }
        dominant_name, dominant_score = max(scores.items(), key=lambda item: item[1])
        supporting_scores = [value for name, value in scores.items() if name != dominant_name]
        supporting_average = sum(supporting_scores) / len(supporting_scores)

        if dominant_score >= 0.82 and max(supporting_scores) <= 0.58:
            scores[dominant_name] = clamp_score(dominant_score * 0.35 + supporting_average * 0.65)
            signals.append(
                "Only one heuristic family strongly suggested AI generation, so the local detector reduced that single-signal spike until other evidence agreed."
            )

        if (
            scores["artifact"] > 0.66
            and scores["metadata"] <= 0.52
            and scores["frequency"] <= 0.52
            and stats["local_noise"] > 0.0045
            and stats["high_frequency_ratio"] > 0.2
        ):
            scores["artifact"] = clamp_score(scores["artifact"] * 0.3 + ((scores["metadata"] + scores["frequency"]) / 2) * 0.7)
            signals.append(
                "Camera-like texture and frequency evidence reduced a lone artifact spike to avoid overcalling edited real photos."
            )

        return scores["metadata"], scores["artifact"], scores["frequency"], list(dict.fromkeys(signals))
