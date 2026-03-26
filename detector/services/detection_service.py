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

    def analyze_uploaded_media(
        self,
        file_path: str,
        source_type: str,
        source_metadata: dict | None = None,
    ) -> DetectionOutcome:
        request_metadata = dict(source_metadata or {})
        use_external_providers = not self._should_prefer_fast_local_only(request_metadata, source_type)

        if source_type == SourceTypes.IMAGE:
            return self.analyze_image(
                file_path,
                source_metadata=request_metadata,
                use_external_providers=use_external_providers,
            )
        if source_type == SourceTypes.VIDEO:
            return self.analyze_video(
                file_path,
                source_metadata=request_metadata,
                use_external_providers=use_external_providers,
            )
        raise ValidationError("Unsupported uploaded media type.")

    def analyze_image(
        self,
        image_path: str,
        source_metadata: dict | None = None,
        *,
        use_external_providers: bool = True,
    ) -> DetectionOutcome:
        request_metadata = dict(source_metadata or {})
        local_result, final_source_metadata, local_breakdown = self.local_image_detector.detect(
            image_path,
            external_metadata=request_metadata,
        )
        provider_results = [local_result]
        if use_external_providers:
            for provider in self.provider_registry.image_providers():
                provider_results.append(provider.detect_image(image_path, source_metadata=final_source_metadata))
        else:
            for provider in self.provider_registry.image_providers():
                provider_results.append(
                    provider.skipped("External provider queries were skipped to keep this mobile upload responsive.")
                )

        return self.score_aggregator.combine(
            provider_results,
            source_metadata=final_source_metadata,
            local_breakdown=local_breakdown,
        )

    def analyze_video(
        self,
        video_path: str,
        source_metadata: dict | None = None,
        *,
        use_external_providers: bool = True,
    ) -> DetectionOutcome:
        request_metadata = dict(source_metadata or {})
        local_result, source_metadata, local_breakdown = self.local_video_detector.detect(
            video_path,
            source_metadata=request_metadata,
        )
        provider_results = [local_result]
        if use_external_providers:
            for provider in self.provider_registry.video_providers():
                provider_results.append(provider.detect_video(video_path, source_metadata=source_metadata))
        else:
            for provider in self.provider_registry.video_providers():
                provider_results.append(
                    provider.skipped("External provider queries were skipped to keep this mobile upload responsive.")
                )

        return self.score_aggregator.combine(
            provider_results,
            source_metadata=source_metadata,
            local_breakdown=local_breakdown,
        )

    def _should_prefer_fast_local_only(self, source_metadata: dict, source_type: str) -> bool:
        if not source_metadata:
            return False

        if source_metadata.get("prefer_fast_analysis") or source_metadata.get("slow_connection") or source_metadata.get("save_data"):
            return True

        try:
            original_bytes = int(float(source_metadata.get("original_bytes") or 0))
        except (TypeError, ValueError):
            original_bytes = 0

        if source_type == SourceTypes.VIDEO:
            return bool(source_metadata.get("mobile_browser") and original_bytes >= 8 * 1024 * 1024)

        return bool(source_metadata.get("mobile_browser") and original_bytes >= 5 * 1024 * 1024)
