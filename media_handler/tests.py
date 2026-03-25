import contextlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework.exceptions import ValidationError

from media_handler.constants import SourceTypes
from media_handler.services.fetchers import _fetch_facebook_preview
from media_handler.services.url_utils import classify_source_url, normalize_public_url
from media_handler.services.video_utils import extract_video_metadata, sample_video_frames


class URLUtilityTests(SimpleTestCase):
    def test_normalize_public_url_adds_https(self):
        normalized = normalize_public_url("youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(normalized, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_classify_source_url_identifies_youtube(self):
        source_type = classify_source_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(source_type, SourceTypes.YOUTUBE)


class FacebookPreviewFetchTests(SimpleTestCase):
    @override_settings(ENABLE_URL_AUDIO_ANALYSIS=True, ENABLE_AUDIO_ANALYSIS=True)
    @patch("media_handler.services.fetchers._download_remote_image")
    @patch("media_handler.services.fetchers._download_remote_video")
    @patch("media_handler.services.fetchers._requests_module")
    def test_facebook_preview_prefers_preview_video_when_available(
        self,
        requests_module_mock,
        download_video_mock,
        download_image_mock,
    ):
        requests_module_mock.return_value.get.return_value = MagicMock(
            status_code=200,
            text="""
                <meta property="og:video" content="https://video.xx.fbcdn.net/sample.mp4" />
                <meta property="og:image" content="https://scontent.xx.fbcdn.net/sample.jpg" />
                <meta property="og:title" content="Public post" />
            """,
        )
        download_video_mock.return_value = "preview.mp4"

        snapshot = _fetch_facebook_preview("https://www.facebook.com/public-post")

        self.assertEqual(snapshot.analysis_type, SourceTypes.VIDEO)
        self.assertEqual(snapshot.metadata["preview_media_type"], "video")
        download_video_mock.assert_called_once()
        download_image_mock.assert_not_called()

    @override_settings(ENABLE_URL_AUDIO_ANALYSIS=True, ENABLE_AUDIO_ANALYSIS=True)
    @patch("media_handler.services.fetchers._download_remote_image")
    @patch("media_handler.services.fetchers._download_remote_video")
    @patch("media_handler.services.fetchers._requests_module")
    def test_facebook_preview_falls_back_to_image_when_preview_video_download_fails(
        self,
        requests_module_mock,
        download_video_mock,
        download_image_mock,
    ):
        requests_module_mock.return_value.get.return_value = MagicMock(
            status_code=200,
            text="""
                <meta property="og:video" content="https://video.xx.fbcdn.net/sample.mp4" />
                <meta property="og:image" content="https://scontent.xx.fbcdn.net/sample.jpg" />
                <meta property="og:title" content="Public post" />
            """,
        )
        download_video_mock.side_effect = ValidationError("preview video too large")
        download_image_mock.return_value = "preview.jpg"

        snapshot = _fetch_facebook_preview("https://www.facebook.com/public-post")

        self.assertEqual(snapshot.analysis_type, SourceTypes.IMAGE)
        self.assertEqual(snapshot.metadata["preview_media_type"], "image")
        download_video_mock.assert_called_once()
        download_image_mock.assert_called_once()


class VideoUtilityFallbackTests(SimpleTestCase):
    @patch("media_handler.services.video_utils._resolve_ffprobe_binary", return_value="ffprobe")
    @patch("media_handler.services.video_utils._load_cv2", return_value=None)
    @patch("media_handler.services.video_utils.subprocess.run")
    def test_extract_video_metadata_uses_ffprobe_when_opencv_is_missing(
        self,
        run_mock,
        load_cv2_mock,
        resolve_ffprobe_mock,
    ):
        run_mock.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "avg_frame_rate": "30000/1001",
                            "nb_frames": "180",
                            "width": 1280,
                            "height": 720,
                            "duration": "6.0",
                        }
                    ]
                }
            ),
        )

        metadata = extract_video_metadata("sample.mp4")

        self.assertEqual(metadata["width"], 1280)
        self.assertEqual(metadata["height"], 720)
        self.assertEqual(metadata["frame_count"], 180)
        self.assertAlmostEqual(metadata["fps"], 29.97, places=2)
        self.assertEqual(metadata["duration_seconds"], 6.0)
        load_cv2_mock.assert_called_once()
        resolve_ffprobe_mock.assert_called_once()

    @patch("media_handler.services.video_utils.extract_video_metadata", return_value={"duration_seconds": 4.0})
    @patch("media_handler.services.video_utils._resolve_ffmpeg_binary", return_value="ffmpeg")
    @patch("media_handler.services.video_utils._load_cv2", return_value=None)
    @patch("media_handler.services.video_utils.subprocess.run")
    def test_sample_video_frames_uses_ffmpeg_when_opencv_is_missing(
        self,
        run_mock,
        load_cv2_mock,
        resolve_ffmpeg_mock,
        metadata_mock,
    ):
        def create_frame(command, capture_output, text, timeout, check):
            output_pattern = command[-1]
            output_dir = Path(output_pattern).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 360), color=(120, 140, 180)).save(output_dir / "frame-001.png", format="PNG")
            Image.new("RGB", (640, 360), color=(122, 142, 182)).save(output_dir / "frame-002.png", format="PNG")
            return MagicMock(returncode=0, stderr="")

        run_mock.side_effect = create_frame
        workspace_tmp = Path.cwd() / "tmp"
        workspace_tmp.mkdir(exist_ok=True)
        temp_dir = workspace_tmp / "video-frame-test"
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        class FixedTemporaryDirectory:
            def __enter__(self):
                return str(temp_dir)

            def __exit__(self, exc_type, exc, tb):
                return False

        try:
            with patch(
                "media_handler.services.video_utils.tempfile.TemporaryDirectory",
                return_value=FixedTemporaryDirectory(),
            ):
                frames = sample_video_frames("sample.mp4", max_seconds=4, max_frames=2, target_width=320)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].width, 320)
        self.assertEqual(frames[0].mode, "RGB")
        load_cv2_mock.assert_called_once()
        resolve_ffmpeg_mock.assert_called_once()
        metadata_mock.assert_called_once()
        run_mock.assert_called_once()

    @patch("media_handler.services.video_utils._resolve_ffmpeg_binary", return_value=None)
    @patch("media_handler.services.video_utils._load_cv2", return_value=None)
    def test_sample_video_frames_raises_clean_error_when_no_video_backend_is_available(
        self,
        load_cv2_mock,
        resolve_ffmpeg_mock,
    ):
        with self.assertRaises(ValidationError):
            sample_video_frames("sample.mp4", max_seconds=4, max_frames=2, target_width=320)

        load_cv2_mock.assert_called_once()
        resolve_ffmpeg_mock.assert_called_once()
