from __future__ import annotations

from rest_framework.exceptions import ValidationError

from detector.services.local_image_detector import LocalImageDetector
from detector.services.local_video_detector import LocalVideoDetector
from detector.services.provider_registry import ProviderRegistry
from detector.services.score_aggregator import ScoreAggregator
from detector.services.scoring import DetectionOutcome
from media_handler.constants import SourceTypes


class DetectionService:
    def __init__(
        self,
        local_image_detector: LocalImageDetector | None = None,
        local_video_detector: LocalVideoDetector | None = None,
        provider_registry: ProviderRegistry | None = None,
        score_aggregator: ScoreAggregator | None = None,
    ):
        self.local_image_detector = local_image_detector or LocalImageDetector()
        self.local_video_detector = local_video_detector or LocalVideoDetector(
            image_detector=self.local_image_detector,
        )
        self.provider_registry = provider_registry or ProviderRegistry()
        self.score_aggregator = score_aggregator or ScoreAggregator()

    def analyze_uploaded_media(self, file_path: str, source_type: str) -> DetectionOutcome:
        if source_type == SourceTypes.IMAGE:
            return self.analyze_image(file_path)
        if source_type == SourceTypes.VIDEO:
            return self.analyze_video(file_path)
        raise ValidationError("Unsupported uploaded media type.")

    def analyze_image(
        self,
        image_path: str,
        source_metadata: dict | None = None,
    ) -> DetectionOutcome:
        local_result, final_source_metadata, local_breakdown = self.local_image_detector.detect(
            image_path,
            external_metadata=source_metadata,
        )
        provider_results = [local_result]
        for provider in self.provider_registry.image_providers():
            provider_results.append(provider.detect_image(image_path, source_metadata=final_source_metadata))

        return self.score_aggregator.combine(
            provider_results,
            source_metadata=final_source_metadata,
            local_breakdown=local_breakdown,
        )

    def analyze_video(
        self,
        video_path: str,
        source_metadata: dict | None = None,
    ) -> DetectionOutcome:
        local_result, source_metadata, local_breakdown = self.local_video_detector.detect(
            video_path,
            source_metadata=source_metadata,
        )
        provider_results = [local_result]
        for provider in self.provider_registry.video_providers():
            provider_results.append(provider.detect_video(video_path, source_metadata=source_metadata))

        return self.score_aggregator.combine(
            provider_results,
            source_metadata=source_metadata,
            local_breakdown=local_breakdown,
        )
