from detector.services.audio_analysis import AudioAnalysisResult, LightweightAudioAnalyzer


class LocalAudioDetector(LightweightAudioAnalyzer):
    """Separate entry point for local audio heuristics in the provider-based pipeline."""


__all__ = ["AudioAnalysisResult", "LocalAudioDetector"]
