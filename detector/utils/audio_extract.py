from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from dataclasses import dataclass, field
from pathlib import Path


NO_AUDIO_STREAM_MARKERS = (
    "stream map '0:a:0' matches no streams",
    "output file #0 does not contain any stream",
    "contains no audio stream",
    "cannot find a matching stream for unlabeled input pad",
)


@dataclass(slots=True)
class AudioExtractionResult:
    used: bool
    summary: str
    reason: str
    path: str = ""
    used_ffmpeg: bool = False
    sample_rate: int = 0
    duration_seconds: float = 0.0
    cleanup_paths: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def skipped(cls, summary: str, reason: str) -> "AudioExtractionResult":
        return cls(used=False, summary=summary, reason=reason)

    def cleanup(self):
        for path in self.cleanup_paths:
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)


def extract_audio_clip(
    source_path: str,
    *,
    max_duration_seconds: int,
    sample_rate: int,
    timeout_seconds: int,
    ffmpeg_binary: str | None = None,
) -> AudioExtractionResult:
    suffix = Path(source_path).suffix.lower()
    if suffix == ".wav":
        return _extract_wave_clip(
            source_path,
            max_duration_seconds=max_duration_seconds,
            sample_rate=sample_rate,
        )

    resolved_ffmpeg = ffmpeg_binary or shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg"))
    if not resolved_ffmpeg:
        return AudioExtractionResult.skipped(
            "Audio analysis was skipped because this deployment cannot find ffmpeg. Install ffmpeg or set FFMPEG_BINARY to enable video-audio checks.",
            reason="ffmpeg_unavailable",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
        output_path = handle.name

    command = [
        resolved_ffmpeg,
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-i",
        source_path,
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-t",
        str(max_duration_seconds),
        "-f",
        "wav",
        output_path,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        with contextlib.suppress(FileNotFoundError):
            os.remove(output_path)
        return AudioExtractionResult.skipped(
            "Audio analysis timed out, so the detector continued with visual-only scoring.",
            reason="ffmpeg_timeout",
        )

    stderr = (completed.stderr or "").lower()
    if completed.returncode != 0:
        with contextlib.suppress(FileNotFoundError):
            os.remove(output_path)
        if any(marker in stderr for marker in NO_AUDIO_STREAM_MARKERS):
            return AudioExtractionResult.skipped(
                "No usable audio stream was detected in the uploaded video.",
                reason="no_audio_stream",
            )
        return AudioExtractionResult.skipped(
            "Audio extraction failed, so the detector continued with visual-only scoring.",
            reason="ffmpeg_failed",
        )

    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 44:
        with contextlib.suppress(FileNotFoundError):
            os.remove(output_path)
        return AudioExtractionResult.skipped(
            "No usable audio stream was detected in the uploaded video.",
            reason="no_audio_stream",
        )

    extracted_sample_rate, duration_seconds = _wave_properties(output_path)
    return AudioExtractionResult(
        used=True,
        summary="Audio clip prepared with ffmpeg.",
        reason="analyzed",
        path=output_path,
        used_ffmpeg=True,
        sample_rate=extracted_sample_rate,
        duration_seconds=duration_seconds,
        cleanup_paths=[output_path],
    )


def _extract_wave_clip(source_path: str, *, max_duration_seconds: int, sample_rate: int) -> AudioExtractionResult:
    try:
        with wave.open(source_path, "rb") as wav_file:
            channel_count = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            source_rate = wav_file.getframerate()
            source_frame_count = wav_file.getnframes()
            requested_frame_count = min(source_frame_count, int(source_rate * max_duration_seconds))
            raw_frames = wav_file.readframes(requested_frame_count)
    except wave.Error:
        return AudioExtractionResult.skipped(
            "Audio analysis could not read the extracted WAV clip.",
            reason="wave_read_failed",
        )

    try:
        pcm_samples = _decode_pcm_samples(raw_frames, sample_width)
    except ValueError:
        return AudioExtractionResult.skipped(
            "Audio analysis skipped an unsupported WAV encoding.",
            reason="unsupported_wave_encoding",
        )

    if channel_count > 1:
        mono_samples = []
        for index in range(0, len(pcm_samples), channel_count):
            frame = pcm_samples[index:index + channel_count]
            mono_samples.append(sum(frame) / len(frame))
    else:
        mono_samples = pcm_samples

    resampled = _resample_nearest(mono_samples, source_rate=source_rate, target_rate=sample_rate)
    clipped_samples = [int(max(-32768, min(32767, round(value)))) for value in resampled]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
        output_path = handle.name

    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(_encode_pcm16(clipped_samples))

    _, duration_seconds = _wave_properties(output_path)
    return AudioExtractionResult(
        used=True,
        summary="Audio clip prepared with the built-in WAV fallback.",
        reason="analyzed",
        path=output_path,
        used_ffmpeg=False,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        cleanup_paths=[output_path],
    )


def _decode_pcm_samples(raw_frames: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        values = array("B", raw_frames)
        return [sample - 128 for sample in values]

    if sample_width == 2:
        values = array("h")
        values.frombytes(raw_frames)
        if sys.byteorder != "little":
            values.byteswap()
        return list(values)

    if sample_width == 4:
        values = array("i")
        values.frombytes(raw_frames)
        if sys.byteorder != "little":
            values.byteswap()
        return [int(sample / 65536) for sample in values]

    raise ValueError("Unsupported PCM width.")


def _encode_pcm16(samples: list[int]) -> bytes:
    values = array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def _resample_nearest(samples: list[int] | list[float], *, source_rate: int, target_rate: int) -> list[float]:
    if not samples or source_rate <= 0 or target_rate <= 0:
        return []

    if source_rate == target_rate:
        return [float(sample) for sample in samples]

    target_length = max(1, int(len(samples) * target_rate / source_rate))
    resampled = []
    for index in range(target_length):
        source_index = min(len(samples) - 1, int(index * source_rate / target_rate))
        resampled.append(float(samples[source_index]))
    return resampled


def _wave_properties(path: str) -> tuple[int, float]:
    with wave.open(path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
    duration_seconds = round(frame_count / sample_rate, 4) if sample_rate else 0.0
    return sample_rate, duration_seconds
