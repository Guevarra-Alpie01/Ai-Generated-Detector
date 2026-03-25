from __future__ import annotations

import copy
import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from results.models import DetectionResult


def hash_uploaded_file(file_obj) -> str:
    digest = hashlib.sha256()
    for chunk in file_obj.chunks():
        digest.update(chunk)

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    return digest.hexdigest()


def find_recent_upload_result(content_sha256: str, source_type: str) -> DetectionResult | None:
    ttl_seconds = int(getattr(settings, "UPLOAD_RESULT_CACHE_SECONDS", 0) or 0)
    if ttl_seconds <= 0 or not content_sha256:
        return None

    cutoff = timezone.now() - timedelta(seconds=ttl_seconds)
    return (
        DetectionResult.objects.filter(
            source_type=source_type,
            content_sha256=content_sha256,
            created_at__gte=cutoff,
        )
        .exclude(result_label="")
        .order_by("-created_at")
        .first()
    )


def find_recent_url_result(source_url: str, source_type: str) -> DetectionResult | None:
    ttl_seconds = int(getattr(settings, "URL_RESULT_CACHE_SECONDS", 0) or 0)
    if ttl_seconds <= 0 or not source_url:
        return None

    cutoff = timezone.now() - timedelta(seconds=ttl_seconds)
    return (
        DetectionResult.objects.filter(
            source_type=source_type,
            source_url=source_url,
            created_at__gte=cutoff,
        )
        .exclude(result_label="")
        .order_by("-created_at")
        .first()
    )


def clone_cached_result(
    cached_result: DetectionResult,
    *,
    source_type: str,
    original_filename: str = "",
    source_url: str = "",
    content_sha256: str = "",
) -> DetectionResult:
    source_metadata = copy.deepcopy(cached_result.source_metadata or {})
    source_metadata["cached_result"] = True
    source_metadata["cached_from_result_id"] = cached_result.id

    score_breakdown = copy.deepcopy(cached_result.score_breakdown or {})
    if isinstance(score_breakdown, dict):
        score_breakdown["cached_result"] = True

    provider_summary = copy.deepcopy(cached_result.provider_summary or {})
    provider_summary["cache"] = {
        "hit": True,
        "source_result_id": cached_result.id,
    }

    return DetectionResult.objects.create(
        source_type=source_type,
        content_sha256=content_sha256,
        source_url=source_url,
        original_filename=original_filename,
        result_label=cached_result.result_label,
        confidence_score=cached_result.confidence_score,
        details=cached_result.details,
        provider_summary=provider_summary,
        provider_used=copy.deepcopy(cached_result.provider_used or []),
        fallback_used=cached_result.fallback_used,
        signals=copy.deepcopy(cached_result.signals or []),
        audio_analysis_used=cached_result.audio_analysis_used,
        score_breakdown=score_breakdown,
        source_metadata=source_metadata,
        raw_local_result=copy.deepcopy(cached_result.raw_local_result or {}),
        raw_illuminarty_result=copy.deepcopy(cached_result.raw_illuminarty_result or {}),
        raw_reality_defender_result=copy.deepcopy(cached_result.raw_reality_defender_result or {}),
    )
