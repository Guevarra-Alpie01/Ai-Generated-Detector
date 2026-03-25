from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from detector.serializers import URLDetectionSerializer, UploadDetectionSerializer
from detector.services.detection_service import DetectionService
from detector.services.scoring import DetectionOutcome
from detector.throttling import DetectionBurstRateThrottle, DetectionSustainedRateThrottle
from detector.utils.url_media_extract import PublicMediaSnapshot, fetch_public_media_snapshot
from media_handler.constants import SourceTypes
from media_handler.services.image_utils import build_upload_name
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


def _persist_detection_outcome(result: DetectionResult, outcome: DetectionOutcome) -> None:
    result.result_label = outcome.label
    result.confidence_score = outcome.confidence
    result.details = outcome.details
    result.provider_summary = outcome.provider_summary
    result.provider_used = outcome.providers_used
    result.fallback_used = outcome.fallback_used
    result.signals = outcome.signals
    result.score_breakdown = outcome.breakdown
    result.source_metadata = outcome.source_metadata
    result.audio_analysis_used = bool(outcome.breakdown.get("audio_analysis_used", False))
    result.raw_local_result = outcome.raw_provider_results.get("local", {})
    result.raw_illuminarty_result = outcome.raw_provider_results.get("illuminarty", {})
    result.raw_reality_defender_result = outcome.raw_provider_results.get("reality_defender", {})
    result.save(
        update_fields=[
            "result_label",
            "confidence_score",
            "details",
            "provider_summary",
            "provider_used",
            "fallback_used",
            "signals",
            "score_breakdown",
            "source_metadata",
            "audio_analysis_used",
            "raw_local_result",
            "raw_illuminarty_result",
            "raw_reality_defender_result",
        ]
    )


class UploadDetectionAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [DetectionBurstRateThrottle, DetectionSustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = UploadDetectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        source_type = serializer.validated_data["source_type"]
        detection_service = DetectionService()

        result = DetectionResult(
            source_type=source_type,
            original_filename=uploaded_file.name,
        )
        result.uploaded_file.save(build_upload_name(uploaded_file.name), uploaded_file, save=True)

        try:
            outcome = detection_service.analyze_uploaded_media(result.uploaded_file.path, source_type)
        except ValidationError:
            result.uploaded_file.delete(save=False)
            result.delete()
            raise
        except Exception as exc:
            result.uploaded_file.delete(save=False)
            result.delete()
            raise APIException(f"Detection failed unexpectedly: {exc}") from exc

        _persist_detection_outcome(result, outcome)

        return Response(
            {
                "message": "Detection completed successfully.",
                "result": DetectionResultSerializer(result, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class URLDetectionAPIView(APIView):
    throttle_classes = [DetectionBurstRateThrottle, DetectionSustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = URLDetectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        normalized_url = serializer.validated_data["normalized_url"]
        source_type = serializer.validated_data["source_type"]
        detection_service = DetectionService()
        snapshot: PublicMediaSnapshot | None = None

        try:
            snapshot = fetch_public_media_snapshot(normalized_url, source_type)
            outcome = detection_service.analyze_image(
                snapshot.local_path,
                source_metadata=snapshot.metadata,
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise APIException(f"URL detection failed unexpectedly: {exc}") from exc
        finally:
            if snapshot is not None:
                snapshot.cleanup()

        result = DetectionResult.objects.create(
            source_type=source_type,
            source_url=normalized_url,
            result_label=outcome.label,
            confidence_score=outcome.confidence,
            details=outcome.details,
            provider_summary=outcome.provider_summary,
            provider_used=outcome.providers_used,
            fallback_used=outcome.fallback_used,
            signals=outcome.signals,
            score_breakdown=outcome.breakdown,
            source_metadata=outcome.source_metadata,
            audio_analysis_used=bool(outcome.breakdown.get("audio_analysis_used", False)),
            raw_local_result=outcome.raw_provider_results.get("local", {}),
            raw_illuminarty_result=outcome.raw_provider_results.get("illuminarty", {}),
            raw_reality_defender_result=outcome.raw_provider_results.get("reality_defender", {}),
        )

        return Response(
            {
                "message": "URL analysis completed successfully.",
                "result": DetectionResultSerializer(result, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )
