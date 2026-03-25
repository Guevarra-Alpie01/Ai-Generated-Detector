from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from django.conf import settings


def ensure_temp_dir(*segments: str) -> Path:
    target = Path(settings.TEMP_ANALYSIS_DIR)
    for segment in segments:
        target /= segment
    target.mkdir(parents=True, exist_ok=True)
    return target


def delete_file_quietly(path: str | Path | None) -> None:
    if not path:
        return
    with contextlib.suppress(FileNotFoundError):
        Path(path).unlink()


def sanitize_json_payload(payload: Any, *, max_chars: int | None = None) -> dict | list | str | int | float | bool | None:
    max_chars = max_chars or settings.PROVIDER_RAW_MAX_CHARS
    try:
        normalized = json.loads(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        normalized = {"payload": str(payload)}

    serialized = json.dumps(normalized, ensure_ascii=True, sort_keys=True)
    if len(serialized) <= max_chars:
        return normalized

    return {
        "truncated": True,
        "original_length": len(serialized),
        "payload_preview": serialized[:max_chars],
    }
