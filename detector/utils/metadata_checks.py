from __future__ import annotations

from django.conf import settings


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
    }

    for keyword in settings.AI_METADATA_KEYWORDS:
        if keyword in lowered_values:
            notes.append(f"Metadata references `{keyword}`, which is commonly associated with AI generation.")
            return 0.98, notes

    camera_hits = [key for key in camera_metadata_keys if metadata.get(key)]
    if camera_hits:
        notes.append("Camera acquisition metadata is present, which strongly supports a real capture pipeline.")
        return (0.08 if len(camera_hits) >= 3 else 0.16), notes

    software_value = str(metadata.get("Software", "")).strip()
    format_name = str(metadata.get("image_format", "")).upper()
    descriptive_entries = [
        key for key, value in metadata.items() if key not in technical_keys and key != "Software" and value
    ]

    if software_value:
        notes.append("Software metadata exists but does not explicitly identify an AI generator.")
        return 0.46, notes

    if format_name == "PNG" and not descriptive_entries:
        notes.append(
            "This PNG export has no acquisition metadata, which is slightly more common for rendered media than direct camera captures."
        )
        return 0.56, notes

    if format_name == "JPEG" and metadata.get("icc_profile_present") and not descriptive_entries:
        notes.append(
            "The file keeps JPEG color-profile data, which is common for camera photos but not conclusive on its own."
        )
        return 0.44, notes

    if descriptive_entries:
        notes.append("Metadata is present but does not clearly identify either a camera or an AI generator.")
        return 0.48, notes

    notes.append(
        "No embedded image metadata was available for cross-checking, so the decision leans more on visible artifacts."
    )
    return 0.5, notes
