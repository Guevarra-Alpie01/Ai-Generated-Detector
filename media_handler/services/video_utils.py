from __future__ import annotations

import math

from PIL import Image
from rest_framework.exceptions import ValidationError


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise ValidationError(
            "Video analysis requires `opencv-python-headless`. Install dependencies before using MP4 detection."
        ) from exc
    return cv2


def extract_video_metadata(video_path: str) -> dict:
    cv2 = _load_cv2()
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValidationError("The uploaded MP4 file could not be opened for analysis.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    capture.release()

    duration = round(frame_count / fps, 2) if fps else 0
    return {
        "fps": round(fps, 2),
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }


def sample_video_frames(video_path: str, max_seconds: int, max_frames: int, target_width: int):
    cv2 = _load_cv2()
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValidationError("The uploaded MP4 file could not be read.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps else 0
    analysis_duration = min(duration, max_seconds) if duration else max_seconds
    effective_frame_count = int(analysis_duration * fps) if fps else frame_count

    if effective_frame_count <= 0:
        capture.release()
        return []

    samples = []
    step = max(1, math.floor(effective_frame_count / max_frames))

    for index in range(0, effective_frame_count, step):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        if pil_image.width > target_width:
            height = int(pil_image.height * (target_width / pil_image.width))
            pil_image = pil_image.resize((target_width, max(1, height)))
        samples.append(pil_image)
        if len(samples) >= max_frames:
            break

    capture.release()
    return samples
