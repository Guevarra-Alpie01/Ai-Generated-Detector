from __future__ import annotations

import contextlib
import json
import uuid
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


@contextlib.contextmanager
def temporary_uploaded_file(file_obj, original_name: str):
    suffix = Path(original_name).suffix.lower() or ".bin"
    temp_dir = ensure_temp_dir("uploads")
    temp_path = temp_dir / f"upload-{uuid.uuid4().hex}{suffix}"

    try:
        with temp_path.open("wb") as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        yield temp_path
    finally:
        delete_file_quietly(temp_path)


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
