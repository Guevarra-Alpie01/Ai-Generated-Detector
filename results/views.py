from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from detector.throttling import ResultsHistoryRateThrottle
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


def _client_session_key(request) -> str:
    return (request.headers.get("X-Client-Session", "") or request.data.get("session_key", "") or "").strip()[:64]


class DetectionResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DetectionResultSerializer
    throttle_classes = [ResultsHistoryRateThrottle]

    def get_queryset(self):
        client_session_key = _client_session_key(self.request)
        if not client_session_key:
            return DetectionResult.objects.none()

        queryset = DetectionResult.objects.filter(client_session_key=client_session_key)
        source_type = self.request.query_params.get("source_type")
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        return queryset


class ResetDetectionHistoryAPIView(APIView):
    throttle_classes = [ResultsHistoryRateThrottle]

    def post(self, request, *args, **kwargs):
        client_session_key = _client_session_key(request)
        if not client_session_key:
            return Response(status=status.HTTP_204_NO_CONTENT)

        queryset = DetectionResult.objects.filter(client_session_key=client_session_key)
        for result in queryset.iterator():
            if result.uploaded_file:
                result.uploaded_file.delete(save=False)
        queryset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
