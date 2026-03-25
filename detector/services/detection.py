from __future__ import annotations

import statistics

from django.conf import settings
from rest_framework.exceptions import ValidationError

from detector.services.scoring import ComponentAssessment, DetectionOutcome, label_from_probability, weighted_score
from detector.utils.image_analysis import analyse_image_statistics
from media_handler.services.image_utils import load_preprocessed_image
from media_handler.services.video_utils import extract_video_metadata, sample_video_frames


class OptionalOnnxImageScorer:
    """Hook for a future tiny ONNX classifier.

    The free-plan-friendly default is heuristic-only scoring. If a very small
    ONNX model is added later, this class is where it plugs in without changing
    the API surface.
    """

    def score(self, image) -> tuple[float, str]:
        model_path = settings.AI_DETECTION_MODEL_PATH
        if not model_path:
            return 0.5, "No ONNX model configured; using heuristic scoring only."
        return 0.5, "ONNX model path configured, but model-specific preprocessing is not wired yet."


class DetectionOrchestrator:
    def __init__(self):
        self.model_scorer = OptionalOnnxImageScorer()

    def detect_image(self, image_path: str, external_metadata: dict | None = None) -> DetectionOutcome:
        image, metadata = load_preprocessed_image(image_path, max_dimension=settings.MAX_IMAGE_DIMENSION)
        if external_metadata:
            metadata.update(external_metadata)

        assessment = self._assess_image(image, metadata)
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
        frame_probabilities = []
        model_scores = []
        artifact_scores = []
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
            model_scores.append(assessment.model_score)
            artifact_scores.append(assessment.artifact_score)
            notes.extend(assessment.notes[:1])

        frame_score = sum(frame_probabilities) / len(frame_probabilities)
        metadata_score, metadata_notes = self._score_video_metadata(video_metadata)
        notes.extend(metadata_notes)

        if len(frame_probabilities) > 1:
            deviation = statistics.pstdev(frame_probabilities)
            temporal_consistency = max(0.0, 0.7 - deviation * 2)
        else:
            temporal_consistency = 0.45

        ai_probability = weighted_score(
            {
                "model_score": sum(model_scores) / len(model_scores),
                "metadata_score": metadata_score,
                "artifact_score": sum(artifact_scores) / len(artifact_scores),
                "frame_score": max(frame_score, temporal_consistency),
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
                "model_score": round(sum(model_scores) / len(model_scores), 4),
                "metadata_score": round(metadata_score, 4),
                "artifact_score": round(sum(artifact_scores) / len(artifact_scores), 4),
                "frame_score": round(max(frame_score, temporal_consistency), 4),
                "temporal_consistency": round(temporal_consistency, 4),
                "ai_probability": ai_probability,
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
        )

    def _score_image_metadata(self, metadata: dict) -> tuple[float, list[str]]:
        notes: list[str] = []
        lowered_values = " ".join(str(value).lower() for value in metadata.values())

        for keyword in settings.AI_METADATA_KEYWORDS:
            if keyword in lowered_values:
                notes.append(f"Metadata references `{keyword}`, which is commonly associated with AI generation.")
                return 0.95, notes

        if metadata.get("Software"):
            notes.append("Software metadata exists but does not explicitly identify an AI generator.")
            return 0.32, notes

        if metadata:
            notes.append("Image metadata is sparse, which is mildly suspicious but common after social uploads.")
            return 0.38, notes

        notes.append("No embedded image metadata was available for cross-checking.")
        return 0.4, notes

    def _score_image_artifacts(self, stats: dict) -> tuple[float, list[str]]:
        score = 0.24
        notes: list[str] = []

        if stats["edge_density"] < 0.055:
            score += 0.20
            notes.append("Edge density is unusually low, suggesting over-smoothed surfaces.")
        elif stats["edge_density"] > 0.23:
            score += 0.10
            notes.append("Edges appear overly crisp, which can happen in synthetic renders.")
        else:
            score -= 0.04

        if stats["local_noise"] < 0.025:
            score += 0.14
            notes.append("Local texture noise is limited compared with typical camera sensor patterns.")
        else:
            score -= 0.05

        if stats["entropy"] < 5.3:
            score += 0.12
            notes.append("Tonal entropy is low, which can indicate synthetic texture repetition.")
        elif stats["entropy"] > 6.6:
            score -= 0.05

        if stats["saturation"] > 0.55 and stats["contrast"] < 0.18:
            score += 0.10
            notes.append("High saturation combined with soft contrast is a recurring AI-artifact pattern.")

        if 0.08 <= stats["edge_density"] <= 0.18 and stats["local_noise"] >= 0.03:
            score -= 0.05

        return max(0.0, min(1.0, round(score, 4))), notes

    def _score_video_metadata(self, metadata: dict) -> tuple[float, list[str]]:
        score = 0.28
        notes: list[str] = []

        fps = metadata.get("fps", 0)
        duration = metadata.get("duration_seconds", 0)
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not fps or fps < 10:
            score += 0.10
            notes.append("Frame rate is unusually low for organic capture.")
        elif fps > 60:
            score += 0.08
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

        return max(0.0, min(1.0, round(score, 4))), notes
