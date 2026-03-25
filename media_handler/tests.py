from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from media_handler.constants import SourceTypes
from media_handler.services.fetchers import _fetch_facebook_preview
from media_handler.services.url_utils import classify_source_url, normalize_public_url


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
