from django.test import SimpleTestCase

from media_handler.constants import SourceTypes
from media_handler.services.url_utils import classify_source_url, normalize_public_url


class URLUtilityTests(SimpleTestCase):
    def test_normalize_public_url_adds_https(self):
        normalized = normalize_public_url("youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(normalized, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_classify_source_url_identifies_youtube(self):
        source_type = classify_source_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(source_type, SourceTypes.YOUTUBE)
