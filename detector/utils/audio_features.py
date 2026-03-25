from __future__ import annotations

import math
import statistics
import sys
import wave
from array import array
from dataclasses import asdict, dataclass


FREQUENCY_BINS = (150, 300, 600, 1200, 2400, 3600)


@dataclass(slots=True)
class AudioFeatureSummary:
    sample_rate: int
    duration_seconds: float
    frame_count: int
    silence_ratio: float
    active_ratio: float
    activity_burst_rate: float
    voiced_frame_ratio: float
    rms_mean: float
    rms_variation: float
    zcr_mean: float
    zcr_variation: float
    centroid_mean: float
    centroid_variation: float
    bandwidth_mean: float
    pitch_mean: float | None
    pitch_variation: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def extract_audio_features(wav_path: str, *, max_duration_seconds: int | None = None) -> AudioFeatureSummary:
    sample_rate, samples = _read_wave_samples(wav_path, max_duration_seconds=max_duration_seconds)
    if not samples:
        return AudioFeatureSummary(
            sample_rate=sample_rate,
            duration_seconds=0.0,
            frame_count=0,
            silence_ratio=1.0,
            active_ratio=0.0,
            activity_burst_rate=0.0,
            voiced_frame_ratio=0.0,
            rms_mean=0.0,
            rms_variation=0.0,
            zcr_mean=0.0,
            zcr_variation=0.0,
            centroid_mean=0.0,
            centroid_variation=0.0,
            bandwidth_mean=0.0,
            pitch_mean=None,
            pitch_variation=None,
        )

    frame_size = max(1, int(sample_rate * 0.04))
    frame_step = frame_size

    frames: list[list[int]] = []
    rms_values: list[float] = []
    zcr_values: list[float] = []
    centroid_values: list[float] = []
    bandwidth_values: list[float] = []
    pitch_values: list[float | None] = []

    for start in range(0, len(samples) - frame_size + 1, frame_step):
        frame = samples[start:start + frame_size]
        frames.append(frame)
        rms_values.append(_rms(frame))
        zcr_values.append(_zero_crossing_rate(frame))
        centroid, bandwidth = _spectral_shape(frame, sample_rate)
        centroid_values.append(centroid)
        bandwidth_values.append(bandwidth)
        pitch_values.append(_estimate_pitch(frame, sample_rate))

    duration_seconds = round(len(samples) / sample_rate, 4) if sample_rate else 0.0
    if not frames:
        return AudioFeatureSummary(
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
            frame_count=0,
            silence_ratio=1.0,
            active_ratio=0.0,
            activity_burst_rate=0.0,
            voiced_frame_ratio=0.0,
            rms_mean=0.0,
            rms_variation=0.0,
            zcr_mean=0.0,
            zcr_variation=0.0,
            centroid_mean=0.0,
            centroid_variation=0.0,
            bandwidth_mean=0.0,
            pitch_mean=None,
            pitch_variation=None,
        )

    peak_rms = max(rms_values, default=0.0)
    silence_threshold = max(0.008, peak_rms * 0.18)
    active_flags = [value >= silence_threshold for value in rms_values]
    active_indices = [index for index, active in enumerate(active_flags) if active]
    active_rms = [rms_values[index] for index in active_indices] or rms_values
    active_zcr = [zcr_values[index] for index in active_indices] or zcr_values
    active_centroids = [centroid_values[index] for index in active_indices] or centroid_values
    active_bandwidths = [bandwidth_values[index] for index in active_indices] or bandwidth_values
    voiced_pitches = [
        pitch_values[index]
        for index in active_indices
        if pitch_values[index] is not None
    ]

    burst_count = 0
    previous_active = False
    for active in active_flags:
        if active and not previous_active:
            burst_count += 1
        previous_active = active

    active_frame_count = max(1, len(active_indices))
    return AudioFeatureSummary(
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        frame_count=len(frames),
        silence_ratio=round(1 - (len(active_indices) / len(frames)), 4),
        active_ratio=round(len(active_indices) / len(frames), 4),
        activity_burst_rate=round(burst_count / max(duration_seconds, 0.001), 4),
        voiced_frame_ratio=round(len(voiced_pitches) / active_frame_count, 4),
        rms_mean=round(statistics.fmean(active_rms), 4),
        rms_variation=round(_safe_pstdev(active_rms), 4),
        zcr_mean=round(statistics.fmean(active_zcr), 4),
        zcr_variation=round(_safe_pstdev(active_zcr), 4),
        centroid_mean=round(statistics.fmean(active_centroids), 4),
        centroid_variation=round(_safe_pstdev(active_centroids), 4),
        bandwidth_mean=round(statistics.fmean(active_bandwidths), 4),
        pitch_mean=round(statistics.fmean(voiced_pitches), 2) if voiced_pitches else None,
        pitch_variation=round(_safe_pstdev(voiced_pitches), 2) if len(voiced_pitches) > 1 else None,
    )


def _read_wave_samples(wav_path: str, *, max_duration_seconds: int | None) -> tuple[int, list[int]]:
    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channel_count = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        if max_duration_seconds is not None:
            frame_count = min(frame_count, int(sample_rate * max_duration_seconds))
        raw_frames = wav_file.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Audio features expect 16-bit PCM WAV input.")

    values = array("h")
    values.frombytes(raw_frames)
    if sys.byteorder != "little":
        values.byteswap()
    samples = list(values)

    if channel_count > 1:
        mono_samples = []
        for index in range(0, len(samples), channel_count):
            frame = samples[index:index + channel_count]
            mono_samples.append(int(sum(frame) / len(frame)))
        samples = mono_samples

    return sample_rate, samples


def _rms(frame: list[int]) -> float:
    if not frame:
        return 0.0
    energy = sum(sample * sample for sample in frame) / len(frame)
    return math.sqrt(energy) / 32768


def _zero_crossing_rate(frame: list[int]) -> float:
    if len(frame) < 2:
        return 0.0

    crossings = 0
    previous_sign = _sample_sign(frame[0])
    for sample in frame[1:]:
        current_sign = _sample_sign(sample)
        if current_sign and previous_sign and current_sign != previous_sign:
            crossings += 1
        if current_sign:
            previous_sign = current_sign
    return crossings / (len(frame) - 1)


def _sample_sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _spectral_shape(frame: list[int], sample_rate: int) -> tuple[float, float]:
    powers = [_goertzel_power(frame, sample_rate, frequency) for frequency in FREQUENCY_BINS]
    total_power = sum(powers)
    if total_power <= 0:
        return 0.0, 0.0

    nyquist = sample_rate / 2
    centroid = sum(frequency * power for frequency, power in zip(FREQUENCY_BINS, powers)) / total_power
    bandwidth = (
        sum(abs(frequency - centroid) * power for frequency, power in zip(FREQUENCY_BINS, powers)) / total_power
    )
    return centroid / nyquist, bandwidth / nyquist


def _goertzel_power(frame: list[int], sample_rate: int, frequency: int) -> float:
    omega = (2 * math.pi * frequency) / sample_rate
    coeff = 2 * math.cos(omega)
    q0 = 0.0
    q1 = 0.0
    q2 = 0.0

    for sample in frame:
        q0 = coeff * q1 - q2 + sample
        q2 = q1
        q1 = q0

    return max(0.0, q1 * q1 + q2 * q2 - coeff * q1 * q2)


def _estimate_pitch(frame: list[int], sample_rate: int) -> float | None:
    if len(frame) < 80:
        return None

    reduced = frame[::2]
    reduced_rate = max(1, sample_rate // 2)
    mean_value = sum(reduced) / len(reduced)
    centered = [sample - mean_value for sample in reduced]
    energy = sum(sample * sample for sample in centered)
    if energy <= 0:
        return None

    min_lag = max(4, int(reduced_rate / 320))
    max_lag = min(len(centered) - 2, int(reduced_rate / 80))
    if max_lag <= min_lag:
        return None

    best_lag = 0
    best_correlation = 0.0
    for lag in range(min_lag, max_lag + 1):
        correlation = 0.0
        for index in range(len(centered) - lag):
            correlation += centered[index] * centered[index + lag]
        if correlation > best_correlation:
            best_correlation = correlation
            best_lag = lag

    if not best_lag:
        return None

    normalized_correlation = best_correlation / energy
    if normalized_correlation < 0.28:
        return None
    return reduced_rate / best_lag


def _safe_pstdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)
