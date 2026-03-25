from __future__ import annotations

import statistics

from django.conf import settings
from rest_framework.exceptions import ValidationError

from detector.services.local_audio_detector import LocalAudioDetector
from detector.services.local_image_detector import LocalImageDetector
from detector.services.providers.base import ProviderResult
from detector.services.scoring import clamp_score, label_from_probability, weighted_score
from detector.utils.temp_files import sanitize_json_payload
from detector.utils.video_frames import extract_video_metadata, sample_video_frames


class LocalVideoDetector:
    provider_name = "local"

    def __init__(
        self,
        image_detector: LocalImageDetector | None = None,
        audio_detector: LocalAudioDetector | None = None,
    ):
        self.image_detector = image_detector or LocalImageDetector()
        self.audio_detector = audio_detector or LocalAudioDetector()

    def detect(
        self,
        video_path: str,
        source_metadata: dict | None = None,
    ) -> tuple[ProviderResult, dict, dict]:
        frames = sample_video_frames(
            video_path,
            max_seconds=settings.MAX_VIDEO_ANALYSIS_SECONDS,
            max_frames=settings.MAX_VIDEO_FRAMES,
            target_width=settings.MAX_VIDEO_PREVIEW_WIDTH,
        )
        if not frames:
            raise ValidationError("No video frames could be extracted from the uploaded MP4 file.")

        video_metadata = extract_video_metadata(video_path)
        audio_result = self.audio_detector.analyze_video(video_path)
        frame_scores: list[float] = []
        frame_stats: list[dict[str, float]] = []
        frame_summaries: list[dict[str, float | str | None]] = []
        signals: list[str] = []

        for index, frame in enumerate(frames):
            frame_result, _, frame_breakdown = self.image_detector.detect_pil_image(frame, metadata={})
            if frame_result.ai_score is not None:
                frame_scores.append(frame_result.ai_score)
            frame_stats.append(frame_breakdown["analysis_stats"])
            frame_summaries.append(
                {
                    "frame_index": index,
                    "label": frame_result.label,
                    "ai_score": round(frame_result.ai_score or 0.0, 4),
                }
            )
            signals.extend(frame_result.signals[:2])

        frame_mean_score = sum(frame_scores) / len(frame_scores)
        metadata_score, metadata_signals = self._score_video_metadata(video_metadata)
        temporal_score, temporal_signals = self._score_temporal_artifacts(frame_stats, frame_scores)
        signals.extend(metadata_signals)
        signals.extend(temporal_signals)
        signals.extend(audio_result.signals)

        component_scores = {
            "frame_mean_score": frame_mean_score,
            "temporal_score": temporal_score,
            "metadata_score": metadata_score,
            "audio_score": audio_result.audio_score,
        }
        ai_score = weighted_score(component_scores, settings.LOCAL_VIDEO_COMPONENT_WEIGHTS)
        label, confidence = label_from_probability(ai_score)
        unique_signals = list(dict.fromkeys(signals))
        details = (
            "; ".join(unique_signals[:4])
            if unique_signals
            else "Local video heuristics stayed close to neutral and do not support a strong claim."
        )
        frame_score_variance = round(statistics.pvariance(frame_scores), 4) if len(frame_scores) > 1 else 0.0

        breakdown = {
            "label": label,
            "confidence": confidence,
            "ai_score": ai_score,
            "frame_mean_score": round(frame_mean_score, 4),
            "frame_score_variance": frame_score_variance,
            "temporal_score": round(temporal_score, 4),
            "metadata_score": round(metadata_score, 4),
            "frames_sampled": len(frames),
            "frame_summaries": frame_summaries[: settings.MAX_VIDEO_FRAMES],
            "signals": unique_signals,
            **audio_result.as_breakdown(),
        }
        merged_source_metadata = {
            **(source_metadata or {}),
            **video_metadata,
            "frames_sampled": len(frames),
        }
        raw_payload = sanitize_json_payload(
            {
                "video_metadata": merged_source_metadata,
                "frame_mean_score": round(frame_mean_score, 4),
                "frame_score_variance": frame_score_variance,
                "temporal_score": round(temporal_score, 4),
                "metadata_score": round(metadata_score, 4),
                "audio_summary": breakdown.get("audio_summary"),
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
        return result, merged_source_metadata, breakdown

    def _score_video_metadata(self, metadata: dict) -> tuple[float, list[str]]:
        score = 0.5
        notes: list[str] = []

        fps = metadata.get("fps", 0)
        duration = metadata.get("duration_seconds", 0)
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not fps or fps < 10:
            score += 0.12
            notes.append("Frame rate is unusually low for organic capture.")
        elif 20 <= fps <= 60:
            score -= 0.08
        elif fps > 60:
            score += 0.06
            notes.append("Frame rate is unusually high for user-generated social clips.")

        if duration and duration > settings.MAX_VIDEO_ANALYSIS_SECONDS:
            notes.append(
                f"Only the first {settings.MAX_VIDEO_ANALYSIS_SECONDS} seconds were analyzed to stay within CPU limits."
            )

        if width and height:
            ratio = width / height if height else 0
            if ratio and (ratio < 0.5 or ratio > 2.2):
                score += 0.05
                notes.append("Video aspect ratio is unusual and slightly increases uncertainty.")

        if not notes:
            notes.append("Video container metadata looks ordinary for a short social clip.")

        return clamp_score(score), notes

    def _score_temporal_artifacts(
        self,
        frame_stats: list[dict[str, float]],
        frame_scores: list[float],
    ) -> tuple[float, list[str]]:
        if len(frame_scores) <= 1 or len(frame_stats) <= 1:
            return 0.5, ["Only one frame could be sampled, so temporal consistency could not be measured reliably."]

        probability_deviation = statistics.pstdev(frame_scores)
        feature_deltas = []

        for previous, current in zip(frame_stats, frame_stats[1:]):
            feature_deltas.append(
                abs(current["edge_density"] - previous["edge_density"]) * 4
                + abs(current["local_noise"] - previous["local_noise"]) * 16
                + abs(current["detail_residual"] - previous["detail_residual"]) * 10
                + abs(current["saturation"] - previous["saturation"]) * 3
                + abs(current["contrast"] - previous["contrast"]) * 3
            )

        mean_delta = sum(feature_deltas) / len(feature_deltas)
        score = 0.5
        notes: list[str] = []

        if probability_deviation > 0.12:
            score += 0.18
            notes.append("Frame-by-frame scores fluctuate sharply, which can indicate temporal AI artifacts or flicker.")
        elif probability_deviation < 0.04:
            score -= 0.06

        if mean_delta > 0.22:
            score += 0.18
            notes.append("Neighbouring frames change in texture and contrast faster than a stable capture normally would.")
        elif mean_delta < 0.09:
            score -= 0.06
            notes.append("Texture and contrast stay relatively stable across the sampled frames.")

        if not notes:
            notes.append("Temporal artifact checks were mixed across the sampled frames.")

        return clamp_score(score), notes
