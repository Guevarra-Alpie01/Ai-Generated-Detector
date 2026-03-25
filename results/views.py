from rest_framework import viewsets

from detector.throttling import ResultsHistoryRateThrottle
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


class DetectionResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DetectionResultSerializer
    throttle_classes = [ResultsHistoryRateThrottle]

    def get_queryset(self):
        queryset = DetectionResult.objects.all()
        source_type = self.request.query_params.get("source_type")
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        return queryset
