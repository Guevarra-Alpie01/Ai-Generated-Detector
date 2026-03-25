from rest_framework import serializers

from results.models import DetectionResult


class DetectionResultSerializer(serializers.ModelSerializer):
    uploaded_file_url = serializers.SerializerMethodField()
    audio_analysis_used = serializers.SerializerMethodField()
    audio_summary = serializers.SerializerMethodField()

    class Meta:
        model = DetectionResult
        fields = [
            "id",
            "source_type",
            "uploaded_file",
            "uploaded_file_url",
            "source_url",
            "original_filename",
            "result_label",
            "confidence_score",
            "details",
            "score_breakdown",
            "source_metadata",
            "audio_analysis_used",
            "audio_summary",
            "created_at",
        ]
        read_only_fields = fields

    def get_uploaded_file_url(self, obj):
        request = self.context.get("request")
        if not obj.uploaded_file:
            return ""
        if request is None:
            return obj.uploaded_file.url
        return request.build_absolute_uri(obj.uploaded_file.url)

    def get_audio_analysis_used(self, obj):
        breakdown = obj.score_breakdown or {}
        if "audio_analysis_used" in breakdown:
            return bool(breakdown["audio_analysis_used"])

        summary = breakdown.get("audio_summary")
        if isinstance(summary, dict) and "used" in summary:
            return bool(summary["used"])
        return None

    def get_audio_summary(self, obj):
        breakdown = obj.score_breakdown or {}
        summary = breakdown.get("audio_summary")
        if isinstance(summary, dict):
            return summary
        return None
