from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from rest_framework.exceptions import ValidationError


def _load_cv2():
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def extract_video_metadata(video_path: str) -> dict:
    cv2 = _load_cv2()
    if cv2 is None:
        return _extract_video_metadata_with_ffprobe(video_path)

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


def sample_video_frames(
    video_path: str,
    max_seconds: int,
    max_frames: int,
    target_width: int,
    video_metadata: dict | None = None,
):
    cv2 = _load_cv2()
    if cv2 is None:
        return _sample_video_frames_with_ffmpeg(
            video_path,
            max_seconds=max_seconds,
            max_frames=max_frames,
            target_width=target_width,
            video_metadata=video_metadata,
        )

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValidationError("The uploaded MP4 file could not be read.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = float((video_metadata or {}).get("duration_seconds") or 0) or (frame_count / fps if fps else 0)
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


def _extract_video_metadata_with_ffprobe(video_path: str) -> dict:
    ffprobe_binary = _resolve_ffprobe_binary()
    if not ffprobe_binary:
        raise ValidationError(
            "Video analysis requires ffmpeg/ffprobe on this deployment. Set FFMPEG_BINARY or install ffmpeg to enable MP4 detection."
        )

    command = [
        ffprobe_binary,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate,nb_frames,width,height,duration",
        "-of",
        "json",
        video_path,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("Video metadata extraction timed out.") from exc

    if completed.returncode != 0:
        raise ValidationError("The uploaded MP4 file could not be opened for analysis.")

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Video metadata extraction returned an invalid response.") from exc

    streams = payload.get("streams") or []
    if not streams:
        raise ValidationError("The uploaded MP4 file does not contain a readable video stream.")

    stream = streams[0]
    fps = _parse_frame_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    frame_count = int(float(stream.get("nb_frames") or 0) or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = round(float(stream.get("duration") or 0.0), 2)

    if not duration and fps and frame_count:
        duration = round(frame_count / fps, 2)
    if not frame_count and fps and duration:
        frame_count = int(duration * fps)

    return {
        "fps": round(fps, 2),
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }


def _sample_video_frames_with_ffmpeg(
    video_path: str,
    *,
    max_seconds: int,
    max_frames: int,
    target_width: int,
    video_metadata: dict | None = None,
):
    ffmpeg_binary = _resolve_ffmpeg_binary()
    if not ffmpeg_binary:
        raise ValidationError(
            "Video frame extraction requires ffmpeg on this deployment. Set FFMPEG_BINARY or install ffmpeg to enable MP4 detection."
        )

    metadata = video_metadata or extract_video_metadata(video_path)
    duration = float(metadata.get("duration_seconds") or 0.0)
    analysis_duration = min(duration, max_seconds) if duration else float(max_seconds)
    if analysis_duration <= 0 or max_frames <= 0:
        return []

    samples = []
    with tempfile.TemporaryDirectory(prefix="aidetector-frames-") as temp_dir:
        output_pattern = str(Path(temp_dir) / "frame-%03d.png")
        sample_rate = max_frames / max(analysis_duration, 1.0)
        command = [
            ffmpeg_binary,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-t",
            str(round(analysis_duration, 3)),
            "-i",
            video_path,
            "-vf",
            f"fps={sample_rate:.4f},scale=min(iw\\,{target_width}):-2:flags=lanczos",
            "-frames:v",
            str(max_frames),
            output_pattern,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(12, int(analysis_duration * 2) + 6),
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed = None

        if completed is None or completed.returncode != 0:
            return []

        for output_path in sorted(Path(temp_dir).glob("frame-*.png"))[:max_frames]:
            if not os.path.exists(output_path):
                continue
            with Image.open(output_path) as frame_image:
                pil_image = frame_image.convert("RGB")
                if pil_image.width > target_width:
                    height = int(pil_image.height * (target_width / pil_image.width))
                    pil_image = pil_image.resize((target_width, max(1, height)))
                samples.append(pil_image.copy())

    return samples


def _resolve_ffmpeg_binary() -> str | None:
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    return shutil.which("ffmpeg")


def _resolve_ffprobe_binary() -> str | None:
    configured = os.environ.get("FFMPEG_PROBE_BINARY", "").strip()
    if configured:
        return configured

    ffmpeg_binary = _resolve_ffmpeg_binary()
    if ffmpeg_binary:
        ffmpeg_path = Path(ffmpeg_binary)
        sibling_probe = ffmpeg_path.with_name("ffprobe")
        if sibling_probe.exists():
            return str(sibling_probe)

    return shutil.which("ffprobe")


def _parse_frame_rate(value: str | None) -> float:
    if not value:
        return 0.0

    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            numerator_value = float(numerator)
            denominator_value = float(denominator)
        except ValueError:
            return 0.0
        if not denominator_value:
            return 0.0
        return numerator_value / denominator_value

    try:
        return float(value)
    except ValueError:
        return 0.0
