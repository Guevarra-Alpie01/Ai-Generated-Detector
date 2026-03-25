from rest_framework import serializers

from results.models import DetectionResult


class DetectionResultSerializer(serializers.ModelSerializer):
    uploaded_file_url = serializers.SerializerMethodField()
    providers_used = serializers.SerializerMethodField()
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
            "providers_used",
            "fallback_used",
            "signals",
            "provider_summary",
            "score_breakdown",
            "source_metadata",
            "audio_analysis_used",
            "audio_summary",
            "raw_local_result",
            "raw_illuminarty_result",
            "raw_reality_defender_result",
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

    def get_providers_used(self, obj):
        providers = obj.provider_used or []
        if isinstance(providers, list):
            return providers
        summary = obj.provider_summary or {}
        successful = summary.get("successful")
        return successful if isinstance(successful, list) else []

    def get_audio_analysis_used(self, obj):
        if obj.audio_analysis_used is not None:
            return bool(obj.audio_analysis_used)

        breakdown = obj.score_breakdown or {}
        if "audio_analysis_used" in breakdown:
            return bool(breakdown["audio_analysis_used"])

        local_breakdown = breakdown.get("local")
        if isinstance(local_breakdown, dict) and "audio_analysis_used" in local_breakdown:
            return bool(local_breakdown["audio_analysis_used"])

        summary = breakdown.get("audio_summary")
        if isinstance(summary, dict) and "used" in summary:
            return bool(summary["used"])
        return None

    def get_audio_summary(self, obj):
        breakdown = obj.score_breakdown or {}
        summary = breakdown.get("audio_summary")
        if isinstance(summary, dict):
            return summary
        local_breakdown = breakdown.get("local")
        if isinstance(local_breakdown, dict):
            nested_summary = local_breakdown.get("audio_summary")
            if isinstance(nested_summary, dict):
                return nested_summary
        return None
