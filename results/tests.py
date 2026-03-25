from django.test import TestCase

from media_handler.constants import SourceTypes
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


class DetectionResultModelTests(TestCase):
    def test_string_representation_uses_available_source(self):
        result = DetectionResult.objects.create(
            source_type=SourceTypes.YOUTUBE,
            source_url="https://www.youtube.com/watch?v=example",
            result_label="Likely real",
            confidence_score=72.0,
        )
        self.assertIn("youtube.com", str(result))

    def test_serializer_normalizes_legacy_percent_confidence_values(self):
        result = DetectionResult.objects.create(
            source_type=SourceTypes.IMAGE,
            original_filename="legacy-score.jpg",
            result_label="Likely real",
            confidence_score=72.0,
        )

        payload = DetectionResultSerializer(result).data

        self.assertEqual(payload["confidence_score"], 0.72)
