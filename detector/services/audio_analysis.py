from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from detector.services.scoring import clamp_score
from detector.utils.audio_extract import AudioExtractionResult, extract_audio_clip
from detector.utils.audio_features import AudioFeatureSummary, extract_audio_features


@dataclass(slots=True)
class AudioAnalysisResult:
    used: bool
    summary: str
    reason: str
    audio_score: float | None = None
    signals: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str | bool | None] = field(default_factory=dict)

    @classmethod
    def skipped(cls, summary: str, reason: str, **metrics) -> "AudioAnalysisResult":
        return cls(
            used=False,
            summary=summary,
            reason=reason,
            audio_score=None,
            signals=[],
            metrics=metrics,
        )

    def as_breakdown(self) -> dict[str, bool | float | dict]:
        return {
            "audio_analysis_used": self.used,
            "audio_score": self.audio_score,
            "audio_summary": {
                "used": self.used,
                "summary": self.summary,
                "reason": self.reason,
                "signals": self.signals,
                "audio_score": self.audio_score,
                **self.metrics,
            },
        }


class LightweightAudioAnalyzer:
    def analyze_video(self, video_path: str) -> AudioAnalysisResult:
        if not settings.ENABLE_AUDIO_ANALYSIS:
            return AudioAnalysisResult.skipped(
                "Audio analysis is disabled by configuration.",
                reason="disabled",
            )

        extraction = extract_audio_clip(
            video_path,
            max_duration_seconds=settings.MAX_AUDIO_ANALYSIS_SECONDS,
            sample_rate=settings.AUDIO_ANALYSIS_SAMPLE_RATE,
            timeout_seconds=settings.AUDIO_ANALYSIS_TIMEOUT_SECONDS,
            ffmpeg_binary=settings.FFMPEG_BINARY,
        )
        if not extraction.used:
            return AudioAnalysisResult.skipped(
                extraction.summary,
                reason=extraction.reason,
            )

        return self._analyze_extracted_clip(extraction)

    def analyze_wav_clip(self, wav_path: str, *, used_ffmpeg: bool = False) -> AudioAnalysisResult:
        extraction = AudioExtractionResult(
            used=True,
            summary="Audio clip prepared for lightweight heuristic analysis.",
            reason="analyzed",
            path=wav_path,
            used_ffmpeg=used_ffmpeg,
        )
        return self._analyze_extracted_clip(extraction)

    def preview_only_skip(self) -> AudioAnalysisResult:
        return AudioAnalysisResult.skipped(
            "Audio analysis was skipped because URL detection currently analyzes a preview image only.",
            reason="preview_only_url",
        )

    def _analyze_extracted_clip(self, extraction: AudioExtractionResult) -> AudioAnalysisResult:
        try:
            features = extract_audio_features(
                extraction.path,
                max_duration_seconds=settings.MAX_AUDIO_ANALYSIS_SECONDS,
            )
        except Exception:
            return AudioAnalysisResult.skipped(
                "Audio feature extraction failed, so the detector continued with visual-only scoring.",
                reason="feature_extraction_failed",
                ffmpeg_used=extraction.used_ffmpeg,
            )
        finally:
            extraction.cleanup()

        return self._score_features(features, used_ffmpeg=extraction.used_ffmpeg)

    def _score_features(self, features: AudioFeatureSummary, *, used_ffmpeg: bool) -> AudioAnalysisResult:
        metrics = {
            "ffmpeg_used": used_ffmpeg,
            "sample_rate": features.sample_rate,
            "analyzed_seconds": round(features.duration_seconds, 2),
            "silence_ratio": features.silence_ratio,
            "active_ratio": features.active_ratio,
            "activity_burst_rate": features.activity_burst_rate,
            "voiced_frame_ratio": features.voiced_frame_ratio,
            "rms_variation": features.rms_variation,
            "zcr_variation": features.zcr_variation,
            "centroid_variation": features.centroid_variation,
            "pitch_variation": features.pitch_variation,
        }

        if features.frame_count == 0:
            return AudioAnalysisResult.skipped(
                "Audio analysis found an empty clip after extraction.",
                reason="empty_audio_clip",
                **metrics,
            )

        if features.active_ratio < 0.12:
            return AudioAnalysisResult(
                used=True,
                summary="Audio was present, but it was mostly silent, so it did not materially change the score.",
                reason="mostly_silent_audio",
                audio_score=0.5,
                signals=["mostly silent audio"],
                metrics=metrics,
            )

        ai_evidence = 0.0
        real_evidence = 0.0
        signals: list[str] = []
        speech_like = features.voiced_frame_ratio >= 0.18

        if features.rms_variation < 0.035 and features.active_ratio > 0.35:
            ai_evidence += 0.12
            signals.append("uniform energy contour")
        elif features.rms_variation > 0.11:
            real_evidence += 0.07
            signals.append("natural energy variation")

        if speech_like and features.pitch_variation is not None:
            if features.pitch_variation < 20:
                ai_evidence += 0.16
                signals.append("low pitch variation")
            elif features.pitch_variation > 45:
                real_evidence += 0.08
                signals.append("healthy pitch variation")

        if speech_like and features.centroid_variation < 0.05 and features.zcr_variation < 0.025:
            ai_evidence += 0.10
            signals.append("stable spectral shape")
        elif features.centroid_variation > 0.10:
            real_evidence += 0.05
            signals.append("spectral variation looks organic")

        if speech_like and features.silence_ratio < 0.04 and features.activity_burst_rate < 1.0:
            ai_evidence += 0.08
            signals.append("sparse pause structure")
        elif 0.08 <= features.silence_ratio <= 0.45 and 1.0 <= features.activity_burst_rate <= 5.5:
            real_evidence += 0.06
            signals.append("organic pause pattern")

        if not speech_like and features.centroid_variation < 0.03 and features.rms_variation < 0.03:
            ai_evidence += 0.06
            signals.append("static audio texture")

        audio_score = clamp_score(0.5 + ai_evidence - real_evidence)
        if not signals:
            summary = "Audio analysis did not find a strong synthetic-speech signal, so it stayed near neutral."
        else:
            summary = f"Audio analysis found {', '.join(signals[:2])}."

        return AudioAnalysisResult(
            used=True,
            summary=summary,
            reason="analyzed",
            audio_score=audio_score,
            signals=signals,
            metrics=metrics,
        )
