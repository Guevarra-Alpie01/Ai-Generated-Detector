from __future__ import annotations

import statistics

from django.conf import settings
from rest_framework.exceptions import ValidationError

from detector.services.audio_analysis import LightweightAudioAnalyzer
from detector.services.scoring import (
    ComponentAssessment,
    DetectionOutcome,
    clamp_score,
    label_from_probability,
    weighted_score,
)
from detector.utils.image_analysis import analyse_image_statistics
from media_handler.services.image_utils import load_preprocessed_image
from media_handler.services.video_utils import extract_video_metadata, sample_video_frames


class OptionalOnnxImageScorer:
    """Hook for a future tiny ONNX classifier.

    The free-plan-friendly default is heuristic-only scoring. If a very small
    ONNX model is added later, this class is where it plugs in without changing
    the API surface.
    """

    def score(self, image) -> tuple[float | None, str]:
        model_path = settings.AI_DETECTION_MODEL_PATH
        if not model_path:
            return None, ""
        return None, "ONNX model path is configured, but model-specific preprocessing is not wired yet."


class DetectionOrchestrator:
    def __init__(self):
        self.model_scorer = OptionalOnnxImageScorer()
        self.audio_analyzer = LightweightAudioAnalyzer()

    def detect_image(self, image_path: str, external_metadata: dict | None = None) -> DetectionOutcome:
        image, metadata = load_preprocessed_image(image_path, max_dimension=settings.MAX_IMAGE_DIMENSION)
        if external_metadata:
            metadata.update(external_metadata)

        assessment = self._assess_image(image, metadata)
        if self._is_preview_based_source(metadata):
            assessment = self._calibrate_preview_assessment(assessment, metadata)
        ai_probability = weighted_score(
            {
                "model_score": assessment.model_score,
                "metadata_score": assessment.metadata_score,
                "artifact_score": assessment.artifact_score,
            },
            settings.DETECTION_WEIGHTS["image"],
        )
        label, confidence = label_from_probability(ai_probability)
        details = "; ".join(assessment.notes) if assessment.notes else "No dominant synthetic artifacts were detected."

        return DetectionOutcome(
            label=label,
            confidence=confidence,
            details=details,
            breakdown={
                **assessment.as_dict(),
                "ai_probability": ai_probability,
            },
            source_metadata=metadata,
        )

    def detect_video(self, video_path: str) -> DetectionOutcome:
        frames = sample_video_frames(
            video_path,
            max_seconds=settings.MAX_VIDEO_ANALYSIS_SECONDS,
            max_frames=settings.MAX_VIDEO_FRAMES,
            target_width=settings.MAX_VIDEO_PREVIEW_WIDTH,
        )
        if not frames:
            raise ValidationError("No video frames could be extracted from the uploaded MP4 file.")

        video_metadata = extract_video_metadata(video_path)
        audio_analysis = self.audio_analyzer.analyze_video(video_path)
        frame_probabilities = []
        model_scores = []
        artifact_scores = []
        frame_stats = []
        notes: list[str] = []

        for frame in frames:
            assessment = self._assess_image(frame, metadata={})
            frame_ai_probability = weighted_score(
                {
                    "model_score": assessment.model_score,
                    "metadata_score": assessment.metadata_score,
                    "artifact_score": assessment.artifact_score,
                },
                settings.DETECTION_WEIGHTS["image"],
            )
            frame_probabilities.append(frame_ai_probability)
            if assessment.model_score is not None:
                model_scores.append(assessment.model_score)
            artifact_scores.append(assessment.artifact_score)
            frame_stats.append(assessment.analysis_stats)
            notes.extend(assessment.notes[:2])

        frame_score = sum(frame_probabilities) / len(frame_probabilities)
        metadata_score, metadata_notes = self._score_video_metadata(video_metadata)
        notes.extend(metadata_notes)
        temporal_score, temporal_notes = self._score_video_temporal_artifacts(frame_stats, frame_probabilities)
        notes.extend(temporal_notes)
        if audio_analysis.summary:
            notes.append(audio_analysis.summary)
        combined_frame_score = clamp_score(frame_score * 0.7 + temporal_score * 0.3)
        average_model_score = round(sum(model_scores) / len(model_scores), 4) if model_scores else None

        ai_probability = weighted_score(
            {
                "model_score": average_model_score,
                "metadata_score": metadata_score,
                "artifact_score": sum(artifact_scores) / len(artifact_scores),
                "frame_score": combined_frame_score,
                "audio_score": audio_analysis.audio_score,
            },
            settings.DETECTION_WEIGHTS["video"],
        )
        label, confidence = label_from_probability(ai_probability)

        details = "; ".join(dict.fromkeys(notes)) if notes else "Video frames did not expose strong synthetic signals."
        metadata_payload = {
            **video_metadata,
            "frames_sampled": len(frames),
        }

        return DetectionOutcome(
            label=label,
            confidence=confidence,
            details=details,
            breakdown={
                "model_score": average_model_score,
                "metadata_score": round(metadata_score, 4),
                "artifact_score": round(sum(artifact_scores) / len(artifact_scores), 4),
                "frame_score": round(combined_frame_score, 4),
                "temporal_score": round(temporal_score, 4),
                "ai_probability": ai_probability,
                **audio_analysis.as_breakdown(),
                "notes": list(dict.fromkeys(notes)),
            },
            source_metadata=metadata_payload,
        )

    def _assess_image(self, image, metadata: dict) -> ComponentAssessment:
        stats = analyse_image_statistics(image)
        model_score, model_note = self.model_scorer.score(image)
        metadata_score, metadata_notes = self._score_image_metadata(metadata)
        artifact_score, artifact_notes = self._score_image_artifacts(stats)

        notes = []
        notes.extend(metadata_notes)
        notes.extend(artifact_notes)
        if model_note:
            notes.append(model_note)

        metadata.update(
            {
                "analysis_stats": {
                    key: round(value, 4) if isinstance(value, float) else value
                    for key, value in stats.items()
                }
            }
        )

        return ComponentAssessment(
            model_score=model_score,
            metadata_score=metadata_score,
            artifact_score=artifact_score,
            notes=list(dict.fromkeys(notes)),
            analysis_stats=stats,
        )

    def _is_preview_based_source(self, metadata: dict) -> bool:
        return bool(metadata.get("preview_strategy") or metadata.get("provider") in {"youtube", "facebook"})

    def _calibrate_preview_assessment(self, assessment: ComponentAssessment, metadata: dict) -> ComponentAssessment:
        provider = str(metadata.get("provider", "")).lower()
        artifact_baseline = 0.42 if provider == "youtube" else 0.45
        artifact_factor = 0.18 if provider == "youtube" else 0.22
        adjusted_artifact_score = clamp_score(
            artifact_baseline + (assessment.artifact_score - 0.5) * artifact_factor
        )
        adjusted_metadata_score = clamp_score(0.5 + (assessment.metadata_score - 0.5) * 0.2)

        preserved_notes = [
            note
            for note in assessment.notes
            if "Metadata references" in note or "Camera acquisition metadata" in note
        ]
        preview_notes = [
            "This result is based on a platform preview image rather than the original uploaded media.",
            "Thumbnail styling and compression can imitate AI-like artifacts, so preview evidence is weighted conservatively.",
        ]
        if provider == "youtube":
            preview_notes[1] = (
                "YouTube thumbnails often use aggressive edits and compression, so preview evidence is weighted conservatively."
            )

        return ComponentAssessment(
            model_score=assessment.model_score,
            metadata_score=adjusted_metadata_score,
            artifact_score=adjusted_artifact_score,
            notes=list(dict.fromkeys([*preserved_notes, *preview_notes])),
            analysis_stats=assessment.analysis_stats,
        )

    def _score_image_metadata(self, metadata: dict) -> tuple[float, list[str]]:
        notes: list[str] = []
        lowered_values = " ".join(f"{key}:{value}".lower() for key, value in metadata.items())
        camera_metadata_keys = (
            "Make",
            "Model",
            "LensMake",
            "LensModel",
            "DateTimeOriginal",
            "ExposureTime",
            "FNumber",
            "FocalLength",
            "ISOSpeedRatings",
            "PhotographicSensitivity",
        )
        technical_keys = {
            "image_format",
            "color_mode",
            "has_alpha",
            "icc_profile_present",
            "progressive",
            "progression",
            "analysis_stats",
        }

        for keyword in settings.AI_METADATA_KEYWORDS:
            if keyword in lowered_values:
                notes.append(f"Metadata references `{keyword}`, which is commonly associated with AI generation.")
                return 0.98, notes

        camera_hits = [key for key in camera_metadata_keys if metadata.get(key)]
        if camera_hits:
            notes.append(
                "Camera acquisition metadata is present, which strongly supports a real capture pipeline."
            )
            return (0.08 if len(camera_hits) >= 3 else 0.16), notes

        software_value = str(metadata.get("Software", "")).strip()
        format_name = str(metadata.get("image_format", "")).upper()
        descriptive_entries = [
            key for key, value in metadata.items() if key not in technical_keys and key != "Software" and value
        ]

        if software_value:
            notes.append("Software metadata exists but does not explicitly identify an AI generator.")
            return 0.46, notes

        if format_name == "PNG" and not descriptive_entries:
            notes.append(
                "This PNG export has no acquisition metadata, which is slightly more common for rendered media than direct camera captures."
            )
            return 0.56, notes

        if format_name == "JPEG" and metadata.get("icc_profile_present") and not descriptive_entries:
            notes.append(
                "The file keeps JPEG color-profile data, which is common for camera photos but not conclusive on its own."
            )
            return 0.44, notes

        if descriptive_entries:
            notes.append("Metadata is present but does not clearly identify either a camera or an AI generator.")
            return 0.48, notes

        notes.append(
            "No embedded image metadata was available for cross-checking, so the decision leans more on visible artifacts."
        )
        return 0.5, notes

    def _score_image_artifacts(self, stats: dict) -> tuple[float, list[str]]:
        ai_evidence = 0.0
        real_evidence = 0.0
        notes: list[str] = []
        clip_total = stats["shadow_clip"] + stats["highlight_clip"]

        if (
            stats["edge_density"] < 0.016
            and stats["local_noise"] < 0.004
            and stats["detail_residual"] < 0.01
        ):
            if clip_total < 0.004 and stats["saturation"] < 0.28 and 7.1 <= stats["entropy"] <= 7.8:
                real_evidence += 0.22
                notes.append(
                    "Texture is smooth, but the tonal roll-off and restrained colors still look photographic."
                )
            else:
                ai_evidence += 0.22
                notes.append("Textures look unusually smooth, which can happen when generative models suppress natural noise.")
        elif (
            stats["edge_density"] > 0.022
            and stats["detail_residual"] > 0.006
            and stats["saturation_spread"] > 0.18
        ):
            ai_evidence += 0.24
            notes.append("Edges, micro-contrast, and color spread are all elevated, which is common in synthetic renders.")
        elif (
            0.01 <= stats["edge_density"] <= 0.05
            and stats["detail_residual"] <= 0.006
            and stats["saturation_spread"] < 0.16
        ):
            real_evidence += 0.14
            notes.append("Edge strength and texture detail stay within a camera-like range.")

        if clip_total > 0.025:
            ai_evidence += 0.16
            notes.append("Shadows and highlights clip aggressively, which is more common in rendered or heavily synthesized media.")
        elif clip_total < 0.004:
            real_evidence += 0.12
            notes.append("The tonal histogram avoids harsh clipping, which supports a natural capture.")

        if stats["saturation_spread"] > 0.18 and stats["contrast"] >= 0.18:
            ai_evidence += 0.12
            notes.append("Color variation is unusually wide for the observed contrast, hinting at synthetic color transitions.")
        elif stats["saturation_spread"] < 0.14 and stats["saturation"] < 0.26:
            real_evidence += 0.08
            notes.append("Color variation is restrained and consistent with a camera capture.")

        if stats["entropy"] > 7.6 and stats["detail_residual"] > 0.006:
            ai_evidence += 0.10
            notes.append("Very high tonal complexity paired with strong local detail can indicate generated textures.")
        elif 7.1 <= stats["entropy"] <= 7.6 and stats["detail_residual"] < 0.005 and clip_total < 0.01:
            real_evidence += 0.06

        if (
            stats["histogram_fill"] > 0.97
            and stats["saturation_histogram_fill"] > 0.95
            and clip_total > 0.02
        ):
            ai_evidence += 0.08
            notes.append(
                "The export uses almost the full tonal and saturation range, which is more common in rendered imagery than phone photos."
            )

        score = clamp_score(0.5 + ai_evidence - real_evidence)
        if not notes:
            notes.append("Visual artifact checks were mixed, so the image stays near a neutral score.")
        return score, list(dict.fromkeys(notes))

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

    def _score_video_temporal_artifacts(
        self,
        frame_stats: list[dict[str, float]],
        frame_probabilities: list[float],
    ) -> tuple[float, list[str]]:
        if len(frame_probabilities) <= 1 or len(frame_stats) <= 1:
            return 0.5, ["Only one frame could be sampled, so temporal consistency could not be measured reliably."]

        probability_deviation = statistics.pstdev(frame_probabilities)
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
