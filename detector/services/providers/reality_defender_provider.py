from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

from detector.services.provider_quota import ProviderSoftQuotaGuard
from detector.services.providers.base import BaseDetectionProvider, ProviderResult
from detector.services.scoring import clamp_score


class RealityDefenderProvider(BaseDetectionProvider):
    provider_name = "reality_defender"
    terminal_statuses = {"AUTHENTIC", "FAKE", "SUSPICIOUS", "NOT_APPLICABLE", "UNABLE_TO_EVALUATE"}
    pending_statuses = {"PENDING", "PROCESSING", "QUEUED", "UPLOADED"}

    def __init__(self, quota_guard: ProviderSoftQuotaGuard | None = None):
        self.quota_guard = quota_guard or ProviderSoftQuotaGuard(
            self.provider_name,
            settings.REALITY_DEFENDER_SOFT_LIMIT_PER_DAY,
        )

    def detect_image(self, image_path: str, source_metadata: dict | None = None) -> ProviderResult:
        if not settings.REALITY_DEFENDER_ENABLED:
            return self.skipped("Reality Defender is disabled by configuration.")
        if not settings.REALITY_DEFENDER_API_URL or not settings.REALITY_DEFENDER_API_KEY:
            return self.skipped("Reality Defender credentials or API URL are missing.")

        allowed, reason = self.quota_guard.allow_request()
        if not allowed:
            return self.skipped(reason)

        self.quota_guard.record_attempt()

        try:
            request_id, upload_url = self._create_presigned_upload(image_path)
            self._upload_media(upload_url, image_path)
            payload = self._poll_result(request_id)
        except requests.Timeout:
            return self.failed(
                "Reality Defender timed out, so the request continued with the local detector only.",
                raw={"timeout_seconds": settings.REALITY_DEFENDER_TIMEOUT_SECONDS},
            )
        except requests.RequestException as exc:
            return self.failed(
                "Reality Defender could not be reached, so the request continued with the local detector only.",
                raw={"error": str(exc)},
            )
        except ValueError as exc:
            return self.failed(str(exc))

        return self._normalize_payload(payload)

    def detect_audio(self, audio_path: str, source_metadata: dict | None = None) -> ProviderResult:
        return self.skipped("Reality Defender audio support is reserved for a future lightweight rollout.")

    def detect_video(self, video_path: str, source_metadata: dict | None = None) -> ProviderResult:
        return self.skipped("Reality Defender video support is behind a future feature flag in this deployment.")

    def _create_presigned_upload(self, image_path: str) -> tuple[str, str]:
        response = requests.post(
            f"{settings.REALITY_DEFENDER_API_URL.rstrip('/')}/api/files/aws-presigned",
            headers=self._headers(),
            json={"fileName": Path(image_path).name},
            timeout=settings.REALITY_DEFENDER_TIMEOUT_SECONDS,
        )
        self._raise_for_status(response, "Reality Defender presigned upload request")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Reality Defender presigned upload response was not valid JSON.") from exc

        request_id = self._find_first(payload, {"requestId", "request_id", "id"})
        upload_url = self._find_first(payload, {"presignedUrl", "presigned_url", "signedUrl", "signed_url", "url"})
        if not request_id or not upload_url:
            raise ValueError("Reality Defender presigned upload response did not include both a request ID and upload URL.")

        return str(request_id), str(upload_url)

    def _upload_media(self, upload_url: str, image_path: str) -> None:
        with open(image_path, "rb") as image_file:
            response = requests.put(
                upload_url,
                data=image_file,
                timeout=settings.REALITY_DEFENDER_TIMEOUT_SECONDS,
            )
        if response.status_code >= 400:
            raise ValueError(f"Reality Defender upload step returned HTTP {response.status_code}.")

    def _poll_result(self, request_id: str) -> dict[str, Any]:
        url = f"{settings.REALITY_DEFENDER_API_URL.rstrip('/')}/api/media/users/{request_id}"
        attempts = max(1, settings.REALITY_DEFENDER_MAX_POLLS)

        for attempt in range(attempts):
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=settings.REALITY_DEFENDER_TIMEOUT_SECONDS,
            )
            if response.status_code in {202, 404} and attempt < attempts - 1:
                time.sleep(settings.REALITY_DEFENDER_POLL_INTERVAL_SECONDS)
                continue

            self._raise_for_status(response, "Reality Defender result polling")
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Reality Defender result polling returned invalid JSON.") from exc

            status = str(self._find_first(payload, {"status"}) or "").upper()
            if not status or status in self.terminal_statuses:
                return payload
            if status in self.pending_statuses and attempt < attempts - 1:
                time.sleep(settings.REALITY_DEFENDER_POLL_INTERVAL_SECONDS)
                continue
            return payload

        raise ValueError("Reality Defender did not return a ready result within the configured polling budget.")

    def _normalize_payload(self, payload: Any) -> ProviderResult:
        if not isinstance(payload, dict):
            return self.failed("Reality Defender returned an unexpected payload type.", raw=payload)

        status = str(self._find_first(payload, {"status"}) or "").upper()
        reasons = self._collect_reason_strings(payload)
        score = self._normalize_score(self._find_first(payload, {"finalScore", "score", "confidence"}))

        if status == "NOT_APPLICABLE":
            return self.skipped(
                reasons[0] if reasons else "Reality Defender reported that the media was not applicable for this classifier.",
                raw=payload,
                signals=reasons,
            )
        if status == "UNABLE_TO_EVALUATE":
            return self.failed(
                reasons[0] if reasons else "Reality Defender reported that it was unable to evaluate the media.",
                raw=payload,
                signals=reasons,
            )
        if score is None:
            return self.failed(
                "Reality Defender returned JSON, but no safely recognized ensemble score was found.",
                raw=payload,
            )

        signals = []
        if status == "FAKE":
            signals.append("Reality Defender ensemble result flagged the image as manipulated.")
        elif status == "AUTHENTIC":
            signals.append("Reality Defender ensemble result looked authentic.")
        elif status == "SUSPICIOUS":
            signals.append("Reality Defender ensemble result remained suspicious.")

        signals.append(f"Reality Defender ensemble score was {round(score * 100)} out of 100.")
        signals.extend(reasons[:2])
        return self.success(
            ai_score=score,
            signals=signals,
            raw=payload,
            details="Reality Defender returned a usable image score.",
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": settings.REALITY_DEFENDER_API_KEY,
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: requests.Response, stage: str) -> None:
        if response.status_code < 400:
            return

        if response.status_code == 429:
            raise ValueError(f"{stage} hit a quota or rate limit.")
        if response.status_code in {401, 403}:
            raise ValueError(f"{stage} was rejected by the provider credentials.")
        raise ValueError(f"{stage} returned HTTP {response.status_code}.")

    def _normalize_score(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric > 1:
            if numeric <= 100:
                numeric /= 100
            else:
                return None
        if numeric < 0:
            return None
        return clamp_score(numeric)

    def _find_first(self, payload: Any, candidate_keys: set[str], depth: int = 0) -> Any:
        if depth > 4:
            return None
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in candidate_keys:
                    return value
            for value in payload.values():
                found = self._find_first(value, candidate_keys, depth + 1)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload[:8]:
                found = self._find_first(item, candidate_keys, depth + 1)
                if found is not None:
                    return found
        return None

    def _collect_reason_strings(self, payload: Any) -> list[str]:
        reasons: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key.lower() in {"reason", "reasons", "message", "messages"}:
                    if isinstance(value, str) and value.strip():
                        reasons.append(value.strip())
                    elif isinstance(value, list):
                        reasons.extend(str(item).strip() for item in value if str(item).strip())
                elif isinstance(value, (dict, list)):
                    reasons.extend(self._collect_reason_strings(value))
        elif isinstance(payload, list):
            for item in payload[:8]:
                reasons.extend(self._collect_reason_strings(item))
        return list(dict.fromkeys(reasons))
