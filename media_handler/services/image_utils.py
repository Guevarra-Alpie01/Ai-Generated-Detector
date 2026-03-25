from __future__ import annotations

import uuid
from pathlib import Path

from django.utils.text import get_valid_filename
from PIL import ExifTags, Image, ImageOps


def build_upload_name(original_name: str) -> str:
    base_name = Path(original_name).name
    safe_name = get_valid_filename(base_name)
    suffix = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem[:40] or "upload"
    return f"{stem}-{uuid.uuid4().hex[:12]}{suffix}"


def load_preprocessed_image(image_path: str, max_dimension: int = 1280):
    with Image.open(image_path) as source_image:
        metadata = extract_image_metadata(source_image)
        image = ImageOps.exif_transpose(source_image).convert("RGB")
        image.thumbnail((max_dimension, max_dimension))
    return image, metadata


def extract_image_metadata(image) -> dict:
    metadata = {
        "image_format": image.format or "",
        "color_mode": image.mode,
        "has_alpha": "A" in image.getbands(),
    }
    exif = image.getexif()
    if exif:
        for tag_id, value in exif.items():
            if isinstance(value, bytes):
                continue
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            metadata[tag_name] = str(value)

    for key, value in image.info.items():
        if key in {"icc_profile", "exif"} or isinstance(value, bytes):
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = str(value)

    metadata["icc_profile_present"] = "icc_profile" in image.info
    return metadata
