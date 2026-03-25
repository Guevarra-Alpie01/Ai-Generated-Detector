from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from rest_framework.exceptions import ValidationError

from media_handler.constants import FACEBOOK_HOSTS, SourceTypes, YOUTUBE_HOSTS


def normalize_public_url(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        raise ValidationError("A public YouTube or Facebook URL is required.")

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Only HTTP and HTTPS URLs are supported.")
    if not parsed.netloc:
        raise ValidationError("The submitted URL is missing a host.")

    host = parsed.netloc.lower().removeprefix("www.")

    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        video_id = extract_youtube_video_id(candidate)
        return f"https://www.youtube.com/watch?v={video_id}"

    if host in {"facebook.com", "m.facebook.com", "fb.watch"}:
        path = parsed.path.rstrip("/") or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        return f"https://www.facebook.com{path}{query}"

    return f"https://{parsed.netloc.lower()}{parsed.path.rstrip('/') or '/'}"


def classify_source_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host in YOUTUBE_HOSTS:
        return SourceTypes.YOUTUBE
    if host in FACEBOOK_HOSTS:
        return SourceTypes.FACEBOOK
    return None


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host == "youtu.be":
        video_id = parsed.path.strip("/")
    else:
        video_id = parse_qs(parsed.query).get("v", [""])[0]

    if not video_id:
        raise ValidationError("Could not determine the YouTube video ID from the submitted URL.")
    return video_id
