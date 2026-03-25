from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

from detector.services.providers.base import BaseDetectionProvider, ProviderResult
from detector.services.scoring import clamp_score


class IlluminartyProvider(BaseDetectionProvider):
    provider_name = "illuminarty"

    def detect_image(self, image_path: str, source_metadata: dict | None = None) -> ProviderResult:
        if not settings.ILLUMINARTY_ENABLED:
            return self.skipped("Illuminarty is disabled by configuration.")
        if not settings.ILLUMINARTY_API_URL or not settings.ILLUMINARTY_API_KEY:
            return self.skipped("Illuminarty credentials or API URL are missing.")

        mime_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        headers = self._build_headers()

        try:
            with open(image_path, "rb") as image_file:
                response = requests.post(
                    settings.ILLUMINARTY_API_URL,
                    headers=headers,
                    files={
                        settings.ILLUMINARTY_UPLOAD_FIELD_NAME: (
                            Path(image_path).name,
                            image_file,
                            mime_type,
                        )
                    },
                    timeout=settings.ILLUMINARTY_TIMEOUT_SECONDS,
                )
        except requests.Timeout:
            return self.failed(
                "Illuminarty timed out, so the request continued with the local detector only.",
                raw={"timeout_seconds": settings.ILLUMINARTY_TIMEOUT_SECONDS},
            )
        except requests.RequestException as exc:
            return self.failed(
                "Illuminarty could not be reached, so the request continued with the local detector only.",
                raw={"error": str(exc)},
            )
        except OSError as exc:
            return self.failed("The image could not be prepared for Illuminarty upload.", raw={"error": str(exc)})

        if response.status_code >= 400:
            return self.failed(
                f"Illuminarty returned HTTP {response.status_code}.",
                raw={"status_code": response.status_code, "body": response.text[:400]},
            )

        try:
            payload = response.json()
        except ValueError:
            return self.failed(
                "Illuminarty returned a non-JSON response, so only the local detector was used.",
                raw={"status_code": response.status_code, "body": response.text[:400]},
            )

        return self._normalize_payload(payload)

    def detect_video(self, video_path: str, source_metadata: dict | None = None) -> ProviderResult:
        return self.skipped("Illuminarty is currently wired for image detection only.")

    def _build_headers(self) -> dict[str, str]:
        token = settings.ILLUMINARTY_API_KEY
        if settings.ILLUMINARTY_AUTH_SCHEME:
            header_value = f"{settings.ILLUMINARTY_AUTH_SCHEME} {token}".strip()
        else:
            header_value = token
        return {settings.ILLUMINARTY_AUTH_HEADER: header_value}

    def _normalize_payload(self, payload: Any) -> ProviderResult:
        if not isinstance(payload, dict):
            return self.failed("Illuminarty returned an unexpected payload type.", raw=payload)

        score = self._extract_score(payload)
        if score is None:
            return self.failed(
                "Illuminarty returned JSON, but no safely recognized score field was found.",
                raw=payload,
            )

        signals: list[str] = []
        classification = self._find_first(payload, {"label", "classification", "prediction", "verdict"})
        if isinstance(classification, str):
            signals.append(f"Illuminarty classification: {classification}.")

        explanation = self._find_first(payload, {"detail", "details", "explanation", "summary"})
        if isinstance(explanation, str) and explanation.strip():
            signals.append(explanation.strip())

        return self.success(
            ai_score=score,
            signals=signals,
            raw=payload,
            details="Illuminarty returned a usable image score.",
        )

    def _extract_score(self, payload: dict[str, Any]) -> float | None:
        # Illuminarty publicly documents API availability, but the public pages do not publish
        # a stable JSON schema. This mapper checks a narrow list of score fields and fails closed
        # if none are present rather than guessing.
        candidate = self._find_first(
            payload,
            {
                "ai_probability",
                "generated_probability",
                "probability",
                "confidence",
                "score",
            },
        )
        return self._normalize_score(candidate)

    def _find_first(self, payload: Any, candidate_keys: set[str], depth: int = 0) -> Any:
        if depth > 3:
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
            for item in payload[:5]:
                found = self._find_first(item, candidate_keys, depth + 1)
                if found is not None:
                    return found
        return None

    def _normalize_score(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
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
