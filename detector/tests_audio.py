import math
import os
import tempfile
import wave
from array import array
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from detector.services.audio_analysis import AudioAnalysisResult, LightweightAudioAnalyzer
from detector.services.local_video_detector import LocalVideoDetector
from detector.services.providers.base import ProviderResult
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


class LocalVideoDetectorTests(SimpleTestCase):
    @patch("detector.services.local_video_detector.extract_video_metadata")
    @patch("detector.services.local_video_detector.sample_video_frames")
    def test_detect_video_includes_audio_breakdown_when_audio_is_used(self, sample_frames_mock, metadata_mock):
        sample_frames_mock.return_value = [object(), object()]
        metadata_mock.return_value = {"fps": 24, "duration_seconds": 5, "width": 1280, "height": 720}

        image_detector = MagicMock()
        image_detector.detect_pil_image.side_effect = [
            (
                ProviderResult.success("local", ai_score=0.62, signals=["frame artifact note"], raw={"score": 0.62}),
                {},
                {
                    "analysis_stats": {
                        "edge_density": 0.03,
                        "local_noise": 0.006,
                        "detail_residual": 0.007,
                        "saturation": 0.2,
                        "contrast": 0.24,
                    }
                },
            ),
            (
                ProviderResult.success("local", ai_score=0.64, signals=["frame artifact note"], raw={"score": 0.64}),
                {},
                {
                    "analysis_stats": {
                        "edge_density": 0.031,
                        "local_noise": 0.0061,
                        "detail_residual": 0.0071,
                        "saturation": 0.201,
                        "contrast": 0.241,
                    }
                },
            ),
        ]
        audio_detector = MagicMock()
        audio_detector.analyze_video.return_value = AudioAnalysisResult(
            used=True,
            summary="Audio analysis found uniform energy contour.",
            reason="analyzed",
            audio_score=0.74,
            signals=["uniform energy contour"],
            metrics={"ffmpeg_used": False},
        )

        detector = LocalVideoDetector(image_detector=image_detector, audio_detector=audio_detector)
        result, source_metadata, breakdown = detector.detect("clip.mp4")

        self.assertEqual(result.provider, "local")
        self.assertTrue(breakdown["audio_analysis_used"])
        self.assertAlmostEqual(breakdown["audio_score"], 0.74)
        self.assertEqual(source_metadata["frames_sampled"], 2)
        sample_frames_mock.assert_called_once()
        audio_detector.analyze_video.assert_called_once_with("clip.mp4", max_duration_seconds=10)

    @patch("detector.services.local_video_detector.extract_video_metadata")
    @patch("detector.services.local_video_detector.sample_video_frames")
    def test_detect_video_stays_available_when_audio_is_skipped(self, sample_frames_mock, metadata_mock):
        sample_frames_mock.return_value = [object(), object()]
        metadata_mock.return_value = {"fps": 24, "duration_seconds": 5, "width": 1280, "height": 720}

        image_detector = MagicMock()
        image_detector.detect_pil_image.side_effect = [
            (
                ProviderResult.success("local", ai_score=0.28, signals=["frame artifact note"], raw={"score": 0.28}),
                {},
                {
                    "analysis_stats": {
                        "edge_density": 0.015,
                        "local_noise": 0.003,
                        "detail_residual": 0.004,
                        "saturation": 0.17,
                        "contrast": 0.2,
                    }
                },
            ),
            (
                ProviderResult.success("local", ai_score=0.3, signals=["frame artifact note"], raw={"score": 0.3}),
                {},
                {
                    "analysis_stats": {
                        "edge_density": 0.016,
                        "local_noise": 0.0032,
                        "detail_residual": 0.0041,
                        "saturation": 0.171,
                        "contrast": 0.201,
                    }
                },
            ),
        ]
        audio_detector = MagicMock()
        audio_detector.analyze_video.return_value = AudioAnalysisResult.skipped(
            "No usable audio stream was detected in the uploaded video.",
            reason="no_audio_stream",
        )

        detector = LocalVideoDetector(image_detector=image_detector, audio_detector=audio_detector)
        result, _, breakdown = detector.detect("clip.mp4")

        self.assertEqual(result.provider, "local")
        self.assertFalse(breakdown["audio_analysis_used"])
        self.assertIsNone(breakdown["audio_score"])
        self.assertEqual(breakdown["audio_summary"]["reason"], "no_audio_stream")

    @patch("detector.services.local_video_detector.extract_video_metadata")
    @patch("detector.services.local_video_detector.sample_video_frames")
    def test_detect_video_uses_fast_mode_limits_for_large_uploads(self, sample_frames_mock, metadata_mock):
        sample_frames_mock.return_value = [object(), object()]
        metadata_mock.return_value = {"fps": 30, "duration_seconds": 32, "width": 2560, "height": 1440}

        image_detector = MagicMock()
        image_detector.detect_pil_image.side_effect = [
            (
                ProviderResult.success("local", ai_score=0.41, signals=["frame note"], raw={"score": 0.41}),
                {},
                {"analysis_stats": {"edge_density": 0.02, "local_noise": 0.004, "detail_residual": 0.005, "saturation": 0.19, "contrast": 0.22}},
            ),
            (
                ProviderResult.success("local", ai_score=0.43, signals=["frame note"], raw={"score": 0.43}),
                {},
                {"analysis_stats": {"edge_density": 0.021, "local_noise": 0.0042, "detail_residual": 0.0051, "saturation": 0.191, "contrast": 0.221}},
            ),
        ]
        audio_detector = MagicMock()
        audio_detector.analyze_video.return_value = AudioAnalysisResult.skipped(
            "Audio was skipped in fast mode.",
            reason="fast_mode_skip",
        )

        detector = LocalVideoDetector(image_detector=image_detector, audio_detector=audio_detector)
        _, source_metadata, breakdown = detector.detect("clip.mp4")

        sample_frames_mock.assert_called_once_with(
            "clip.mp4",
            max_seconds=6,
            max_frames=2,
            target_width=640,
            video_metadata=metadata_mock.return_value,
        )
        audio_detector.analyze_video.assert_called_once_with("clip.mp4", max_duration_seconds=4)
        self.assertTrue(source_metadata["fast_mode_applied"])
        self.assertTrue(breakdown["fast_mode_applied"])
