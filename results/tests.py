from django.test import TestCase

from media_handler.constants import SourceTypes
from results.models import DetectionResult


class DetectionResultModelTests(TestCase):
    def test_string_representation_uses_available_source(self):
        result = DetectionResult.objects.create(
            source_type=SourceTypes.YOUTUBE,
            source_url="https://www.youtube.com/watch?v=example",
            result_label="Likely real",
            confidence_score=72.0,
        )
        self.assertIn("youtube.com", str(result))
