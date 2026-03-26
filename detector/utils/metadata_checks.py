from __future__ import annotations

from django.conf import settings


EDITING_SOFTWARE_KEYWORDS = (
    "photoshop",
    "adobe photoshop",
    "lightroom",
    "camera raw",
    "snapseed",
    "capture one",
    "luminar",
    "dxo",
    "gimp",
    "affinity photo",
    "pixelmator",
    "picsart",
    "vsco",
    "apple photos",
    "google photos",
    "samsung gallery",
    "canva",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> str:
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            return keyword
    return ""


def assess_image_metadata(metadata: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    lowered_values = " ".join(f"{key}:{value}".lower() for key, value in metadata.items())
    camera_metadata_keys = (
        "Make",
        "Model",
        "LensMake",
        "LensModel",
        "DateTimeOriginal",
        "ExposureTime",
        "FNumber",
        "FocalLength",
        "ISOSpeedRatings",
        "PhotographicSensitivity",
    )
    technical_keys = {
        "image_format",
        "color_mode",
        "has_alpha",
        "icc_profile_present",
        "progressive",
        "progression",
        "analysis_stats",
        "browser_upload_optimized",
        "original_extension",
        "original_bytes",
        "original_mime_type",
        "optimized_bytes",
        "optimized_width",
        "optimized_height",
    }

    for keyword in settings.AI_METADATA_KEYWORDS:
        if keyword in lowered_values:
            notes.append(f"Metadata references `{keyword}`, which is commonly associated with AI generation.")
            return 0.98, notes

    camera_hits = [key for key in camera_metadata_keys if metadata.get(key)]
    software_value = str(metadata.get("Software", "")).strip()
    software_lowered = software_value.lower()
    format_name = str(metadata.get("image_format", "")).upper()
    descriptive_entries = [
        key for key, value in metadata.items() if key not in technical_keys and key != "Software" and value
    ]
    editing_keyword = _contains_any(software_lowered, EDITING_SOFTWARE_KEYWORDS)
    browser_optimized = bool(metadata.get("browser_upload_optimized"))
    original_extension = str(metadata.get("original_extension", "")).lower()

    if camera_hits and editing_keyword:
        notes.append(
            f"Camera metadata survived an editing export through `{editing_keyword}`, which supports a real photo that was enhanced after capture."
        )
        return 0.12, notes

    if camera_hits:
        notes.append("Camera acquisition metadata is present, which strongly supports a real capture pipeline.")
        return (0.08 if len(camera_hits) >= 3 else 0.16), notes

    if editing_keyword:
        notes.append(
            f"Software metadata points to `{editing_keyword}`, which is commonly used for enhancement or retouching rather than AI generation."
        )
        if format_name == "JPEG" or metadata.get("icc_profile_present") or descriptive_entries:
            return 0.34, notes
        return 0.4, notes

    if software_value:
        notes.append("Software metadata exists but looks more like a generic export or edit step than an AI generator.")
        return 0.42, notes

    if browser_optimized:
        notes.append(
            "This upload was optimized in the browser to fit the device or network limits, so missing metadata is treated conservatively."
        )
        if original_extension in {".jpg", ".jpeg", ".heic", ".heif"}:
            return 0.44, notes
        return 0.46, notes

    if format_name == "PNG" and not descriptive_entries:
        notes.append(
            "This PNG export has no acquisition metadata, which slightly increases uncertainty but is not enough to imply full AI generation."
        )
        return 0.52, notes

    if format_name == "JPEG" and metadata.get("icc_profile_present") and not descriptive_entries:
        notes.append(
            "The file keeps JPEG color-profile data, which is common for camera photos and edited exports but not conclusive on its own."
        )
        return 0.4, notes

    if descriptive_entries:
        notes.append("Metadata is present but does not clearly identify either a camera or an AI generator.")
        return 0.46, notes

    notes.append(
        "No embedded image metadata was available for cross-checking, so the decision leans more on visible artifacts."
    )
    return 0.48, notes
