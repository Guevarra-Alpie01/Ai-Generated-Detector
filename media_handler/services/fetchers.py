from __future__ import annotations

import contextlib
import mimetypes
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
    analysis_type: str
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
            analysis_type=SourceTypes.IMAGE,
            local_path=local_path,
            remote_url=candidate,
            metadata={
                "provider": "youtube",
                "video_id": video_id,
                "preview_url": candidate,
                "preview_media_type": "image",
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
    video_tag = (
        soup.find("meta", property="og:video:secure_url")
        or soup.find("meta", property="og:video:url")
        or soup.find("meta", property="og:video")
    )
    title_tag = soup.find("meta", property="og:title")
    preview_url = image_tag["content"].strip() if image_tag and image_tag.get("content") else ""
    preview_video_url = video_tag["content"].strip() if video_tag and video_tag.get("content") else ""

    if settings.ENABLE_URL_AUDIO_ANALYSIS and settings.ENABLE_AUDIO_ANALYSIS and preview_video_url:
        try:
            local_video_path = _download_remote_video(preview_video_url)
            return PublicMediaSnapshot(
                source_type=SourceTypes.FACEBOOK,
                analysis_type=SourceTypes.VIDEO,
                local_path=local_video_path,
                remote_url=preview_video_url,
                metadata={
                    "provider": "facebook",
                    "preview_url": preview_video_url,
                    "preview_media_type": "video",
                    "page_title": title_tag["content"].strip() if title_tag and title_tag.get("content") else "",
                    "preview_strategy": "open_graph_preview_video",
                    "analysis_note": "A public preview video was available, so bounded local audio and frame analysis were used.",
                },
            )
        except ValidationError:
            # Fall back to the preview image when the preview video is missing, too large,
            # or cannot be downloaded within the configured budget.
            pass

    if not preview_url:
        raise ValidationError("A public Facebook preview image was not found on that page.")

    host = urlparse(preview_url).netloc.lower()
    if not host.endswith(FACEBOOK_MEDIA_HOST_SUFFIXES) and "facebook.com" not in host:
        raise ValidationError("The Facebook preview points to an unsupported remote host.")

    local_path = _download_remote_image(preview_url)
    return PublicMediaSnapshot(
        source_type=SourceTypes.FACEBOOK,
        analysis_type=SourceTypes.IMAGE,
        local_path=local_path,
        remote_url=preview_url,
        metadata={
            "provider": "facebook",
            "preview_url": preview_url,
            "preview_media_type": "image",
            "page_title": title_tag["content"].strip() if title_tag and title_tag.get("content") else "",
            "preview_strategy": "open_graph_preview",
        },
    )


def _download_remote_image(image_url: str) -> str:
    return _download_remote_asset(
        image_url,
        expected_kind="image",
        max_bytes=settings.URL_FETCH_MAX_BYTES,
        default_suffix=".jpg",
        download_error="The remote image could not be downloaded.",
        type_error="The discovered remote asset is not an image.",
    )


def _download_remote_video(video_url: str) -> str:
    return _download_remote_asset(
        video_url,
        expected_kind="video",
        max_bytes=settings.URL_FETCH_MAX_VIDEO_BYTES,
        default_suffix=".mp4",
        download_error="The remote preview video could not be downloaded.",
        type_error="The discovered remote asset is not a video.",
    )


def _download_remote_asset(
    asset_url: str,
    *,
    expected_kind: str,
    max_bytes: int,
    default_suffix: str,
    download_error: str,
    type_error: str,
) -> str:
    requests = _requests_module()
    cache_dir = ensure_temp_dir("url_cache")
    host = urlparse(asset_url).netloc.lower()
    if not host.endswith(FACEBOOK_MEDIA_HOST_SUFFIXES) and "facebook.com" not in host and "ytimg.com" not in host:
        raise ValidationError("The public preview points to an unsupported remote host.")

    with requests.get(
        asset_url,
        stream=True,
        timeout=settings.URL_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AIDetectorBot/1.0)"},
    ) as response:
        if response.status_code >= 400:
            raise ValidationError(download_error)

        content_type = (response.headers.get("Content-Type") or "").lower()
        if expected_kind == "image":
            valid_type = "image" in content_type
        else:
            valid_type = "video" in content_type or (
                content_type in {"application/octet-stream", ""}
                and Path(urlparse(asset_url).path).suffix.lower() in {".mp4", ".m4v", ".mov"}
            )
        if not valid_type:
            raise ValidationError(type_error)

        guessed_suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or default_suffix
        if guessed_suffix == ".jpe":
            guessed_suffix = ".jpg"

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=guessed_suffix, dir=cache_dir) as temp_file:
                temp_path = temp_file.name
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        if expected_kind == "video":
                            raise ValidationError("The remote preview video exceeds the configured download limit.")
                        raise ValidationError("The remote preview image exceeds the configured download limit.")
                    temp_file.write(chunk)
                return temp_path
        except Exception:
            if temp_path:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(temp_path)
            raise
