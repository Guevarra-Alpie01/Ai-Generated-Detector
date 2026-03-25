from __future__ import annotations

import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from detector.services.detection_service import DetectionService
from detector.services.local_image_detector import LocalImageDetector
from detector.services.providers.base import ProviderResult
from detector.services.providers.illuminarty_provider import IlluminartyProvider
from detector.services.providers.reality_defender_provider import RealityDefenderProvider
from detector.services.provider_registry import ProviderRegistry
from detector.services.score_aggregator import ScoreAggregator
from detector.services.scoring import DetectionOutcome, clamp_score, label_from_probability, weighted_score


def build_test_image_bytes(color=(120, 140, 180)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def write_test_image(path: str, color=(120, 140, 180)) -> None:
    Image.new("RGB", (64, 64), color=color).save(path, format="PNG")


class StubLocalImageDetector:
    def __init__(self, ai_score: float):
        self.ai_score = ai_score

    def detect(self, image_path: str, external_metadata: dict | None = None):
        metadata = {"image_format": "PNG", **(external_metadata or {})}
        breakdown = {
            "ai_score": self.ai_score,
            "metadata_score": 0.5,
            "artifact_score": self.ai_score,
            "frequency_score": self.ai_score,
            "signals": ["local heuristic score"],
        }
        return (
            ProviderResult.success(
                "local",
                ai_score=self.ai_score,
                signals=["local heuristic score"],
                raw=breakdown,
                details="Local detector finished.",
            ),
            metadata,
            breakdown,
        )


class StubProvider:
    def __init__(self, provider_name: str, result: ProviderResult):
        self.provider_name = provider_name
        self.result = result

    def detect_image(self, image_path: str, source_metadata: dict | None = None):
        return self.result

    def detect_video(self, video_path: str, source_metadata: dict | None = None):
        return self.result


class StubProviderRegistry:
    def __init__(self, image_providers=None, video_providers=None):
        self._image_providers = image_providers or []
        self._video_providers = video_providers or []

    def image_providers(self):
        return list(self._image_providers)

    def video_providers(self):
        return list(self._video_providers)


class ScoringUtilityTests(SimpleTestCase):
    def test_clamp_score_bounds_value(self):
        self.assertEqual(clamp_score(4), 1.0)
        self.assertEqual(clamp_score(-2), 0.0)

    def test_label_from_probability_uses_uncertain_band(self):
        label, confidence = label_from_probability(0.82, thresholds={"low": 0.35, "high": 0.68})
        self.assertEqual(label, "AI-generated")
        self.assertAlmostEqual(confidence, 0.82)

        uncertain_label, uncertain_confidence = label_from_probability(0.52, thresholds={"low": 0.35, "high": 0.68})
        self.assertEqual(uncertain_label, "Uncertain")
        self.assertGreater(uncertain_confidence, 0.5)

    def test_weighted_score_ignores_missing_components(self):
        score = weighted_score(
            {
                "metadata_score": 0.5,
                "artifact_score": 0.9,
                "frequency_score": None,
            },
            {
                "metadata_score": 0.25,
                "artifact_score": 0.55,
                "frequency_score": 0.20,
            },
        )
        self.assertAlmostEqual(score, 0.775)


class LocalDetectorTests(SimpleTestCase):
    def test_local_image_detector_handles_real_image_path(self):
        local_detector = LocalImageDetector()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
            image_path = image_file.name
        try:
            write_test_image(image_path)
            result, source_metadata, breakdown = local_detector.detect(image_path)
        finally:
            Path(image_path).unlink(missing_ok=True)

        self.assertEqual(result.provider, "local")
        self.assertEqual(result.status, "success")
        self.assertIn(result.label, {"AI-generated", "Likely real", "Uncertain"})
        self.assertIn("analysis_stats", source_metadata)
        self.assertIn("frequency_score", breakdown)


class ProviderBehaviorTests(SimpleTestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
            self.image_path = image_file.name
        write_test_image(self.image_path)

    def tearDown(self):
        Path(self.image_path).unlink(missing_ok=True)

    @override_settings(ILLUMINARTY_ENABLED=False)
    def test_illuminarty_disabled_returns_skipped(self):
        provider = IlluminartyProvider()
        result = provider.detect_image(self.image_path)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.provider, "illuminarty")

    @override_settings(REALITY_DEFENDER_ENABLED=False)
    def test_reality_defender_disabled_returns_skipped(self):
        provider = RealityDefenderProvider()
        result = provider.detect_image(self.image_path)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.provider, "reality_defender")

    @override_settings(
        ILLUMINARTY_ENABLED=True,
        ILLUMINARTY_API_KEY="demo-key",
        ILLUMINARTY_API_URL="https://example.test/illuminarty",
        REALITY_DEFENDER_ENABLED=False,
    )
    @patch("detector.services.providers.illuminarty_provider.requests.post", side_effect=requests.Timeout)
    def test_provider_timeout_falls_back_to_local(self, post_mock):
        service = DetectionService()
        outcome = service.analyze_image(self.image_path)

        self.assertIn("local", outcome.providers_used)
        self.assertTrue(outcome.fallback_used)
        self.assertIn("illuminarty", outcome.provider_summary["failed"])
        post_mock.assert_called_once()

    @override_settings(
        ILLUMINARTY_ENABLED=True,
        ILLUMINARTY_API_KEY="demo-key",
        ILLUMINARTY_API_URL="https://example.test/illuminarty",
        REALITY_DEFENDER_ENABLED=False,
    )
    @patch("detector.services.providers.illuminarty_provider.requests.post")
    def test_malformed_provider_response_keeps_local_result(self, post_mock):
        response = MagicMock(status_code=200)
        response.json.return_value = {"status": "ok", "payload": {"unexpected": "shape"}}
        post_mock.return_value = response

        service = DetectionService()
        outcome = service.analyze_image(self.image_path)

        self.assertEqual(outcome.providers_used, ["local"])
        self.assertIn("illuminarty", outcome.provider_summary["failed"])


class DetectionServiceAggregationTests(SimpleTestCase):
    @override_settings(
        DETECTION_PROVIDER_WEIGHTS={"local": 0.4, "illuminarty": 0.6, "reality_defender": 0.0},
        DETECTION_LABEL_THRESHOLDS={"low": 0.35, "high": 0.68},
    )
    def test_successful_local_plus_illuminarty_merge_path(self):
        registry = StubProviderRegistry(
            image_providers=[
                StubProvider(
                    "illuminarty",
                    ProviderResult.success(
                        "illuminarty",
                        ai_score=0.9,
                        signals=["elevated external score"],
                        raw={"score": 0.9},
                    ),
                )
            ]
        )
        service = DetectionService(
            local_image_detector=StubLocalImageDetector(ai_score=0.4),
            provider_registry=registry,
            score_aggregator=ScoreAggregator(),
        )

        outcome = service.analyze_image("unused.png")

        self.assertEqual(outcome.label, "AI-generated")
        self.assertEqual(outcome.providers_used, ["local", "illuminarty"])
        self.assertTrue(outcome.fallback_used)

    @override_settings(
        DETECTION_PROVIDER_WEIGHTS={"local": 0.55, "illuminarty": 0.0, "reality_defender": 0.45},
        DETECTION_LABEL_THRESHOLDS={"low": 0.35, "high": 0.68},
    )
    def test_successful_local_plus_reality_defender_merge_path(self):
        registry = StubProviderRegistry(
            image_providers=[
                StubProvider(
                    "reality_defender",
                    ProviderResult.success(
                        "reality_defender",
                        ai_score=0.86,
                        signals=["reality defender ensemble score"],
                        raw={"finalScore": 86},
                    ),
                )
            ]
        )
        service = DetectionService(
            local_image_detector=StubLocalImageDetector(ai_score=0.52),
            provider_registry=registry,
            score_aggregator=ScoreAggregator(),
        )

        outcome = service.analyze_image("unused.png")

        self.assertEqual(outcome.providers_used, ["local", "reality_defender"])
        self.assertTrue(outcome.fallback_used)
        self.assertGreater(outcome.breakdown["provider_scores"]["reality_defender"], 0.8)

    @override_settings(
        DETECTION_PROVIDER_WEIGHTS={"local": 0.5, "illuminarty": 0.5, "reality_defender": 0.0},
        DETECTION_LABEL_THRESHOLDS={"low": 0.35, "high": 0.68},
        DETECTION_DISAGREEMENT_SPREAD_THRESHOLD=0.3,
    )
    def test_disagreement_between_providers_produces_uncertain(self):
        aggregator = ScoreAggregator()
        outcome = aggregator.combine(
            [
                ProviderResult.success("local", ai_score=0.15, signals=["camera-like cues"], raw={"score": 0.15}),
                ProviderResult.success(
                    "illuminarty",
                    ai_score=0.88,
                    signals=["external score elevated"],
                    raw={"score": 0.88},
                ),
            ],
            source_metadata={},
            local_breakdown={"ai_score": 0.15},
        )

        self.assertEqual(outcome.label, "Uncertain")
        self.assertIn("providers disagreed", outcome.details.lower())

    @override_settings(ILLUMINARTY_ENABLED=False, REALITY_DEFENDER_ENABLED=False)
    def test_successful_local_only_path(self):
        service = DetectionService(
            local_image_detector=StubLocalImageDetector(ai_score=0.48),
            provider_registry=ProviderRegistry(),
            score_aggregator=ScoreAggregator(),
        )

        outcome = service.analyze_image("unused.png")

        self.assertEqual(outcome.providers_used, ["local"])
        self.assertTrue(outcome.fallback_used)
        self.assertIn("illuminarty", outcome.provider_summary["skipped"])
        self.assertIn("reality_defender", outcome.provider_summary["skipped"])


class DetectionApiResponseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        workspace_tmp = Path.cwd() / "tmp"
        workspace_tmp.mkdir(exist_ok=True)
        self.media_root = tempfile.mkdtemp(prefix="aidetector-media-", dir=workspace_tmp)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    @patch("django.db.models.fields.files.FieldFile.save", autospec=True)
    @patch("detector.views.DetectionService.analyze_uploaded_media")
    def test_upload_api_response_contains_providers_used_and_fallback_used(self, analyze_mock, field_save_mock):
        def fake_field_save(field_file, name, content, save=True):
            field_file.name = name
            if save:
                field_file.instance.save()

        field_save_mock.side_effect = fake_field_save
        analyze_mock.return_value = DetectionOutcome(
            label="AI-generated",
            confidence=0.81,
            details="Combined local analysis with Illuminarty result.",
            breakdown={
                "ai_score": 0.81,
                "provider_scores": {"local": 0.71, "illuminarty": 0.88},
                "audio_analysis_used": False,
            },
            source_metadata={},
            signals=["frequency anomaly detected", "external provider score elevated"],
            providers_used=["local", "illuminarty"],
            fallback_used=True,
            provider_summary={
                "successful": ["local", "illuminarty"],
                "skipped": ["reality_defender"],
                "failed": [],
            },
            raw_provider_results={
                "local": {"ai_score": 0.71},
                "illuminarty": {"score": 0.88},
            },
        )

        response = self.client.post(
            "/api/detect/upload/",
            {
                "file": SimpleUploadedFile("sample.png", build_test_image_bytes(), content_type="image/png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["result"]
        self.assertEqual(payload["providers_used"], ["local", "illuminarty"])
        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["signals"], ["frequency anomaly detected", "external provider score elevated"])
