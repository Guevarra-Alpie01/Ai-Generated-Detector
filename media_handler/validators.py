from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError

from media_handler.constants import IMAGE_EXTENSIONS, IMAGE_MIME_TYPES, SourceTypes, VIDEO_EXTENSIONS, VIDEO_MIME_TYPES


def validate_uploaded_media(file_obj):
    extension = Path(file_obj.name).suffix.lower()
    content_type = (getattr(file_obj, "content_type", "") or "").lower()
    file_size = getattr(file_obj, "size", 0)

    if extension in IMAGE_EXTENSIONS:
        if content_type and content_type not in IMAGE_MIME_TYPES:
            raise ValidationError("Image MIME type is not supported. Use JPG, JPEG, or PNG.")
        if file_size > settings.MAX_IMAGE_UPLOAD_SIZE:
            limit = settings.MAX_IMAGE_UPLOAD_SIZE // (1024 * 1024)
            raise ValidationError(f"Image files must be {limit} MB or smaller.")
        return SourceTypes.IMAGE

    if extension in VIDEO_EXTENSIONS:
        if content_type and content_type not in VIDEO_MIME_TYPES:
            raise ValidationError("Video MIME type is not supported. Use MP4 only.")
        if file_size > settings.MAX_VIDEO_UPLOAD_SIZE:
            limit = settings.MAX_VIDEO_UPLOAD_SIZE // (1024 * 1024)
            raise ValidationError(f"Video files must be {limit} MB or smaller.")
        return SourceTypes.VIDEO

    raise ValidationError("Unsupported file type. Allowed types: JPG, JPEG, PNG, MP4.")
