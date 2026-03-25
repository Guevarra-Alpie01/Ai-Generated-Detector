from detector.services.detection_service import DetectionService


class DetectionOrchestrator:
    """Compatibility shim that now delegates to the provider-based detection service."""

    def __init__(self):
        self.service = DetectionService()
        self.audio_analyzer = self.service.local_video_detector.audio_detector

    def detect_image(self, image_path: str, external_metadata: dict | None = None):
        return self.service.analyze_image(image_path, source_metadata=external_metadata)

    def detect_video(self, video_path: str):
        return self.service.analyze_video(video_path)
