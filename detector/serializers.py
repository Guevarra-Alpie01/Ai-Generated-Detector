from rest_framework import serializers

from media_handler.services.url_utils import classify_source_url, normalize_public_url
from media_handler.validators import validate_uploaded_media


class UploadDetectionSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate(self, attrs):
        file_obj = attrs["file"]
        attrs["source_type"] = validate_uploaded_media(file_obj)
        return attrs


class URLDetectionSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=500)

    def validate_url(self, value):
        normalized_url = normalize_public_url(value)
        source_type = classify_source_url(normalized_url)
        if source_type is None:
            raise serializers.ValidationError("Only public YouTube and Facebook URLs are supported.")
        self.context["normalized_url"] = normalized_url
        self.context["source_type"] = source_type
        return normalized_url

    def validate(self, attrs):
        attrs["normalized_url"] = self.context["normalized_url"]
        attrs["source_type"] = self.context["source_type"]
        return attrs
