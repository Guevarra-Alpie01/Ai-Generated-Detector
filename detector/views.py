from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from detector.serializers import URLDetectionSerializer, UploadDetectionSerializer
from detector.services.detection import DetectionOrchestrator
from detector.throttling import DetectionBurstRateThrottle, DetectionSustainedRateThrottle
from media_handler.constants import SourceTypes
from media_handler.services.fetchers import PublicMediaSnapshot, fetch_public_media_snapshot
from media_handler.services.image_utils import build_upload_name
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


class UploadDetectionAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [DetectionBurstRateThrottle, DetectionSustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = UploadDetectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        source_type = serializer.validated_data["source_type"]
        orchestrator = DetectionOrchestrator()

        result = DetectionResult(
            source_type=source_type,
            original_filename=uploaded_file.name,
        )
        result.uploaded_file.save(build_upload_name(uploaded_file.name), uploaded_file, save=True)

        try:
            if source_type == SourceTypes.IMAGE:
                outcome = orchestrator.detect_image(result.uploaded_file.path)
            else:
                outcome = orchestrator.detect_video(result.uploaded_file.path)
        except ValidationError:
            result.uploaded_file.delete(save=False)
            result.delete()
            raise
        except Exception as exc:
            result.uploaded_file.delete(save=False)
            result.delete()
            raise APIException(f"Detection failed unexpectedly: {exc}") from exc

        result.result_label = outcome.label
        result.confidence_score = outcome.confidence
        result.details = outcome.details
        result.score_breakdown = outcome.breakdown
        result.source_metadata = outcome.source_metadata
        result.save(
            update_fields=[
                "result_label",
                "confidence_score",
                "details",
                "score_breakdown",
                "source_metadata",
            ]
        )

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
        orchestrator = DetectionOrchestrator()
        snapshot: PublicMediaSnapshot | None = None

        try:
            snapshot = fetch_public_media_snapshot(normalized_url, source_type)
            outcome = orchestrator.detect_image(
                snapshot.local_path,
                external_metadata=snapshot.metadata,
            )
            audio_analysis = orchestrator.audio_analyzer.preview_only_skip()
            outcome.breakdown.update(audio_analysis.as_breakdown())
            outcome.details = (
                f"{outcome.details}; {audio_analysis.summary}"
                if outcome.details
                else audio_analysis.summary
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
            score_breakdown=outcome.breakdown,
            source_metadata=outcome.source_metadata,
        )

        return Response(
            {
                "message": "URL analysis completed successfully.",
                "result": DetectionResultSerializer(result, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )
