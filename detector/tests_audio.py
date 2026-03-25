import math
import os
import shutil
import tempfile
import wave
from array import array
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from detector.services.audio_analysis import AudioAnalysisResult, LightweightAudioAnalyzer
from detector.services.detection import DetectionOrchestrator
from detector.services.scoring import ComponentAssessment, DetectionOutcome
from detector.utils.audio_extract import extract_audio_clip


def write_test_wave(path, segments, sample_rate=16000):
    samples = array("h")
    for kind, duration_seconds, frequency_hz, amplitude in segments:
        frame_count = int(sample_rate * duration_seconds)
        for index in range(frame_count):
            if kind == "silence":
                samples.append(0)
                continue
            phase = 2 * math.pi * frequency_hz * (index / sample_rate)
            value = int(32767 * amplitude * math.sin(phase))
            samples.append(value)

    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())


class AudioExtractionUtilityTests(SimpleTestCase):
    def test_extract_audio_clip_uses_builtin_wave_fallback(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as source_file:
            source_path = source_file.name
        write_test_wave(source_path, [("tone", 1.6, 220, 0.4)])

        result = extract_audio_clip(
            source_path,
            max_duration_seconds=1,
            sample_rate=8000,
            timeout_seconds=2,
        )

        try:
            self.assertTrue(result.used)
            self.assertFalse(result.used_ffmpeg)
            with wave.open(result.path, "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 8000)
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertLessEqual(wav_file.getnframes(), 8100)
        finally:
            result.cleanup()
            os.remove(source_path)

    @patch("detector.utils.audio_extract.shutil.which", return_value=None)
    def test_extract_audio_clip_skips_video_when_ffmpeg_missing(self, which_mock):
        result = extract_audio_clip(
            "sample.mp4",
            max_duration_seconds=8,
            sample_rate=16000,
            timeout_seconds=2,
        )

        self.assertFalse(result.used)
        self.assertEqual(result.reason, "ffmpeg_unavailable")
        which_mock.assert_called_once()

    @patch("detector.utils.audio_extract.shutil.which", return_value="ffmpeg")
    @patch("detector.utils.audio_extract.subprocess.run")
    def test_extract_audio_clip_handles_missing_audio_stream(self, run_mock, which_mock):
        run_mock.return_value = MagicMock(
            returncode=1,
            stderr="Stream map '0:a:0' matches no streams.",
        )

        result = extract_audio_clip(
            "sample.mp4",
            max_duration_seconds=8,
            sample_rate=16000,
            timeout_seconds=2,
        )

        self.assertFalse(result.used)
        self.assertEqual(result.reason, "no_audio_stream")
        which_mock.assert_called_once()
        run_mock.assert_called_once()


class AudioAnalysisServiceTests(SimpleTestCase):
    def test_audio_analyzer_scores_flat_tone_higher_than_varied_clip(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as flat_file:
            flat_path = flat_file.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as varied_file:
            varied_path = varied_file.name

        write_test_wave(
            flat_path,
            [
                ("tone", 2.5, 210, 0.42),
            ],
        )
        write_test_wave(
            varied_path,
            [
                ("tone", 0.5, 180, 0.25),
                ("silence", 0.2, 0, 0),
                ("tone", 0.5, 240, 0.52),
                ("silence", 0.2, 0, 0),
                ("tone", 0.5, 170, 0.32),
                ("silence", 0.15, 0, 0),
                ("tone", 0.45, 280, 0.48),
            ],
        )

        analyzer = LightweightAudioAnalyzer()
        try:
            flat_result = analyzer.analyze_wav_clip(flat_path)
            varied_result = analyzer.analyze_wav_clip(varied_path)
        finally:
            os.remove(flat_path)
            os.remove(varied_path)

        self.assertTrue(flat_result.used)
        self.assertTrue(varied_result.used)
        self.assertIsNotNone(flat_result.audio_score)
        self.assertIsNotNone(varied_result.audio_score)
        self.assertGreater(flat_result.audio_score, varied_result.audio_score)


class VideoDetectionAudioIntegrationTests(SimpleTestCase):
    @patch("detector.services.detection.extract_video_metadata")
    @patch("detector.services.detection.sample_video_frames")
    def test_detect_video_includes_audio_breakdown_when_audio_is_used(self, sample_frames_mock, metadata_mock):
        sample_frames_mock.return_value = [object(), object()]
        metadata_mock.return_value = {"fps": 24, "duration_seconds": 5, "width": 1280, "height": 720}

        assessment = ComponentAssessment(
            model_score=None,
            metadata_score=0.5,
            artifact_score=0.62,
            notes=["frame artifact note"],
            analysis_stats={
                "edge_density": 0.03,
                "local_noise": 0.006,
                "detail_residual": 0.007,
                "saturation": 0.2,
                "contrast": 0.24,
            },
        )

        orchestrator = DetectionOrchestrator()
        orchestrator._assess_image = MagicMock(side_effect=[assessment, assessment])
        orchestrator.audio_analyzer.analyze_video = MagicMock(
            return_value=AudioAnalysisResult(
                used=True,
                summary="Audio analysis found uniform energy contour.",
                reason="analyzed",
                audio_score=0.74,
                signals=["uniform energy contour"],
                metrics={"ffmpeg_used": False},
            )
        )

        outcome = orchestrator.detect_video("clip.mp4")

        self.assertTrue(outcome.breakdown["audio_analysis_used"])
        self.assertAlmostEqual(outcome.breakdown["audio_score"], 0.74)
        self.assertEqual(outcome.breakdown["audio_summary"]["signals"], ["uniform energy contour"])

    @patch("detector.services.detection.extract_video_metadata")
    @patch("detector.services.detection.sample_video_frames")
    def test_detect_video_stays_available_when_audio_is_skipped(self, sample_frames_mock, metadata_mock):
        sample_frames_mock.return_value = [object(), object()]
        metadata_mock.return_value = {"fps": 24, "duration_seconds": 5, "width": 1280, "height": 720}

        assessment = ComponentAssessment(
            model_score=None,
            metadata_score=0.5,
            artifact_score=0.3,
            notes=["frame artifact note"],
            analysis_stats={
                "edge_density": 0.015,
                "local_noise": 0.003,
                "detail_residual": 0.004,
                "saturation": 0.17,
                "contrast": 0.2,
            },
        )

        orchestrator = DetectionOrchestrator()
        orchestrator._assess_image = MagicMock(side_effect=[assessment, assessment])
        orchestrator.audio_analyzer.analyze_video = MagicMock(
            return_value=AudioAnalysisResult.skipped(
                "No usable audio stream was detected in the uploaded video.",
                reason="no_audio_stream",
            )
        )

        outcome = orchestrator.detect_video("clip.mp4")

        self.assertFalse(outcome.breakdown["audio_analysis_used"])
        self.assertIsNone(outcome.breakdown["audio_score"])
        self.assertEqual(outcome.breakdown["audio_summary"]["reason"], "no_audio_stream")

    def test_preview_calibration_reduces_thumbnail_false_positives(self):
        orchestrator = DetectionOrchestrator()
        assessment = ComponentAssessment(
            model_score=None,
            metadata_score=0.48,
            artifact_score=0.86,
            notes=[
                "Shadows and highlights clip aggressively, which is more common in rendered or heavily synthesized media.",
                "Color variation is unusually wide for the observed contrast, hinting at synthetic color transitions.",
            ],
            analysis_stats={},
        )

        calibrated = orchestrator._calibrate_preview_assessment(assessment, {"provider": "youtube"})

        self.assertLess(calibrated.artifact_score, assessment.artifact_score)
        self.assertLess(calibrated.artifact_score, 0.55)
        self.assertIn("platform preview image", " ".join(calibrated.notes))


class UploadDetectionAudioApiTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        workspace_tmp = os.path.join(os.getcwd(), "tmp")
        os.makedirs(workspace_tmp, exist_ok=True)
        self.media_root = tempfile.mkdtemp(prefix="aidetector-media-", dir=workspace_tmp)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    @patch("django.db.models.fields.files.FieldFile.save", autospec=True)
    @patch("detector.views.DetectionOrchestrator.detect_video")
    def test_upload_api_returns_audio_summary_fields(self, detect_video_mock, field_save_mock):
        def fake_field_save(field_file, name, content, save=True):
            field_file.name = name
            if save:
                field_file.instance.save()

        field_save_mock.side_effect = fake_field_save
        detect_video_mock.return_value = DetectionOutcome(
            label="AI-generated",
            confidence=78.4,
            details="Visual anomalies detected. Audio analysis found uniform energy contour.",
            breakdown={
                "ai_probability": 0.784,
                "artifact_score": 0.72,
                "metadata_score": 0.42,
                "audio_score": 0.66,
                "audio_analysis_used": True,
                "audio_summary": {
                    "used": True,
                    "summary": "Audio analysis found uniform energy contour.",
                    "reason": "analyzed",
                    "signals": ["uniform energy contour"],
                    "audio_score": 0.66,
                },
            },
            source_metadata={},
        )

        response = self.client.post(
            "/api/detect/upload/",
            {"file": SimpleUploadedFile("clip.mp4", b"fake-video", content_type="video/mp4")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["result"]
        self.assertTrue(payload["audio_analysis_used"])
        self.assertEqual(payload["audio_summary"]["signals"], ["uniform energy contour"])

    @patch("detector.views.fetch_public_media_snapshot")
    @patch("detector.views.DetectionOrchestrator.detect_image")
    def test_url_api_marks_audio_as_skipped_for_preview_only_sources(self, detect_image_mock, snapshot_mock):
        class DummySnapshot:
            local_path = "preview.jpg"
            metadata = {"provider": "youtube"}

            def cleanup(self):
                return None

        snapshot_mock.return_value = DummySnapshot()
        detect_image_mock.return_value = DetectionOutcome(
            label="Likely real",
            confidence=63.2,
            details="Preview image looked ordinary.",
            breakdown={
                "ai_probability": 0.368,
                "artifact_score": 0.3,
                "metadata_score": 0.41,
            },
            source_metadata={},
        )

        response = self.client.post(
            "/api/detect/url/",
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["result"]
        self.assertFalse(payload["audio_analysis_used"])
        self.assertEqual(payload["audio_summary"]["reason"], "preview_only_url")
        self.assertNotIn("Audio was not analyzed for this URL", payload["details"])
