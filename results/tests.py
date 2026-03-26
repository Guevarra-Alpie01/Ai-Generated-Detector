from django.test import TestCase
from rest_framework.test import APIClient

from media_handler.constants import SourceTypes
from results.models import DetectionResult
from results.serializers import DetectionResultSerializer


class DetectionResultModelTests(TestCase):
    def test_string_representation_uses_available_source(self):
        result = DetectionResult.objects.create(
            client_session_key="session-a",
            source_type=SourceTypes.YOUTUBE,
            source_url="https://www.youtube.com/watch?v=example",
            result_label="Likely real",
            confidence_score=72.0,
        )
        self.assertIn("youtube.com", str(result))

    def test_serializer_normalizes_legacy_percent_confidence_values(self):
        result = DetectionResult.objects.create(
            client_session_key="session-a",
            source_type=SourceTypes.IMAGE,
            original_filename="legacy-score.jpg",
            result_label="Likely real",
            confidence_score=72.0,
        )

        payload = DetectionResultSerializer(result).data

        self.assertEqual(payload["confidence_score"], 0.72)


class DetectionResultSessionIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        DetectionResult.objects.create(
            client_session_key="session-a",
            source_type=SourceTypes.IMAGE,
            original_filename="a.jpg",
            result_label="Likely real",
            confidence_score=0.2,
        )
        DetectionResult.objects.create(
            client_session_key="session-b",
            source_type=SourceTypes.IMAGE,
            original_filename="b.jpg",
            result_label="AI-generated",
            confidence_score=0.8,
        )

    def test_results_endpoint_returns_only_current_session_history(self):
        response = self.client.get("/api/results/", HTTP_X_CLIENT_SESSION="session-a")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["original_filename"], "a.jpg")

    def test_results_endpoint_hides_history_without_session_header(self):
        response = self.client.get("/api/results/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_reset_endpoint_clears_only_matching_session_history(self):
        response = self.client.post("/api/results/reset/", HTTP_X_CLIENT_SESSION="session-a")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(DetectionResult.objects.filter(client_session_key="session-a").exists())
        self.assertTrue(DetectionResult.objects.filter(client_session_key="session-b").exists())
