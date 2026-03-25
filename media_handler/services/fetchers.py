from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from rest_framework.exceptions import ValidationError

from detector.utils.temp_files import ensure_temp_dir
from media_handler.constants import FACEBOOK_MEDIA_HOST_SUFFIXES, SourceTypes
from media_handler.services.url_utils import extract_youtube_video_id


def _requests_module():
    import requests

    return requests


@dataclass(slots=True)
class PublicMediaSnapshot:
    source_type: str
    local_path: str
    remote_url: str
    metadata: dict

    def cleanup(self):
        with contextlib.suppress(FileNotFoundError):
            os.remove(self.local_path)


def fetch_public_media_snapshot(url: str, source_type: str) -> PublicMediaSnapshot:
    if source_type == SourceTypes.YOUTUBE:
        return _fetch_youtube_thumbnail(url)
    if source_type == SourceTypes.FACEBOOK:
        return _fetch_facebook_preview(url)
    raise ValidationError("Unsupported URL source type.")


def _fetch_youtube_thumbnail(url: str) -> PublicMediaSnapshot:
    video_id = extract_youtube_video_id(url)
    candidates = [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]

    for candidate in candidates:
        try:
            local_path = _download_remote_image(candidate)
        except ValidationError:
            continue
        return PublicMediaSnapshot(
            source_type=SourceTypes.YOUTUBE,
            local_path=local_path,
            remote_url=candidate,
            metadata={
                "provider": "youtube",
                "video_id": video_id,
                "preview_url": candidate,
                "preview_strategy": "thumbnail_only",
                "analysis_note": "Thumbnail analysis is used to keep synchronous CPU-only requests short on PythonAnywhere.",
            },
        )

    raise ValidationError("Unable to download a public YouTube thumbnail for the submitted URL.")


def _fetch_facebook_preview(url: str) -> PublicMediaSnapshot:
    requests = _requests_module()
    response = requests.get(
        url,
        timeout=settings.URL_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AIDetectorBot/1.0)"},
    )
    if response.status_code >= 400:
        raise ValidationError("The Facebook URL could not be accessed publicly.")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(response.text, "html.parser")
    image_tag = soup.find("meta", property="og:image")
    title_tag = soup.find("meta", property="og:title")
    preview_url = image_tag["content"].strip() if image_tag and image_tag.get("content") else ""

    if not preview_url:
        raise ValidationError("A public Facebook preview image was not found on that page.")

    host = urlparse(preview_url).netloc.lower()
    if not host.endswith(FACEBOOK_MEDIA_HOST_SUFFIXES) and "facebook.com" not in host:
        raise ValidationError("The Facebook preview points to an unsupported remote host.")

    local_path = _download_remote_image(preview_url)
    return PublicMediaSnapshot(
        source_type=SourceTypes.FACEBOOK,
        local_path=local_path,
        remote_url=preview_url,
        metadata={
            "provider": "facebook",
            "preview_url": preview_url,
            "page_title": title_tag["content"].strip() if title_tag and title_tag.get("content") else "",
            "preview_strategy": "open_graph_preview",
        },
    )


def _download_remote_image(image_url: str) -> str:
    requests = _requests_module()
    cache_dir = ensure_temp_dir("url_cache")

    with requests.get(
        image_url,
        stream=True,
        timeout=settings.URL_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AIDetectorBot/1.0)"},
    ) as response:
        if response.status_code >= 400:
            raise ValidationError("The remote image could not be downloaded.")

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            raise ValidationError("The discovered remote asset is not an image.")

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", dir=cache_dir) as temp_file:
                temp_path = temp_file.name
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > settings.URL_FETCH_MAX_BYTES:
                        raise ValidationError("The remote preview image exceeds the configured download limit.")
                    temp_file.write(chunk)
                return temp_path
        except Exception:
            if temp_path:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(temp_path)
            raise
