import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def env_json(name: str, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, type(default)) else default


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-before-production",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "detector",
    "media_handler",
    "results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "main.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIST_DIR, BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "main.wsgi.application"
ASGI_APPLICATION = "main.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []
if FRONTEND_DIST_DIR.exists():
    STATICFILES_DIRS.append(FRONTEND_DIST_DIR)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

MAX_IMAGE_UPLOAD_SIZE = env_int("MAX_IMAGE_UPLOAD_SIZE", 10 * 1024 * 1024)
MAX_VIDEO_UPLOAD_SIZE = env_int("MAX_VIDEO_UPLOAD_SIZE", 20 * 1024 * 1024)
MAX_IMAGE_DIMENSION = env_int("MAX_IMAGE_DIMENSION", 1280)
UPLOAD_RESULT_CACHE_SECONDS = env_int("UPLOAD_RESULT_CACHE_SECONDS", 24 * 60 * 60)
URL_RESULT_CACHE_SECONDS = env_int("URL_RESULT_CACHE_SECONDS", 6 * 60 * 60)
MAX_VIDEO_ANALYSIS_SECONDS = env_int("MAX_VIDEO_ANALYSIS_SECONDS", 12)
MAX_VIDEO_FRAMES = env_int("MAX_VIDEO_FRAMES", 5)
MAX_VIDEO_PREVIEW_WIDTH = env_int("MAX_VIDEO_PREVIEW_WIDTH", 960)
ENABLE_AUDIO_ANALYSIS = env_bool("ENABLE_AUDIO_ANALYSIS", True)
MAX_AUDIO_ANALYSIS_SECONDS = env_int("MAX_AUDIO_ANALYSIS_SECONDS", 10)
AUDIO_ANALYSIS_SAMPLE_RATE = env_int("AUDIO_ANALYSIS_SAMPLE_RATE", 16000)
AUDIO_ANALYSIS_TIMEOUT_SECONDS = env_int("AUDIO_ANALYSIS_TIMEOUT_SECONDS", 8)
FFMPEG_BINARY = os.environ.get("FFMPEG_BINARY", "")
URL_FETCH_TIMEOUT_SECONDS = env_int("URL_FETCH_TIMEOUT_SECONDS", 8)
URL_FETCH_MAX_BYTES = env_int("URL_FETCH_MAX_BYTES", 10 * 1024 * 1024)
URL_FETCH_MAX_VIDEO_BYTES = env_int("URL_FETCH_MAX_VIDEO_BYTES", min(MAX_VIDEO_UPLOAD_SIZE, 12 * 1024 * 1024))
ENABLE_URL_AUDIO_ANALYSIS = env_bool("ENABLE_URL_AUDIO_ANALYSIS", True)
AI_DETECTION_MODEL_PATH = os.environ.get("AI_DETECTION_MODEL_PATH", "")
AI_METADATA_KEYWORDS = [
    keyword.strip().lower()
    for keyword in os.environ.get(
        "AI_METADATA_KEYWORDS",
        "midjourney,dall-e,stable diffusion,firefly,adobe firefly,synthetic,generated by ai,openai,flux",
    ).split(",")
    if keyword.strip()
]

TEMP_ANALYSIS_DIR = Path(os.environ.get("TEMP_ANALYSIS_DIR", BASE_DIR / "tmp"))
TEMP_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
PROVIDER_RAW_MAX_CHARS = env_int("PROVIDER_RAW_MAX_CHARS", 3000)

LOCAL_IMAGE_WORKING_SIZE = env_int("LOCAL_IMAGE_WORKING_SIZE", 256)
LOCAL_IMAGE_COMPONENT_WEIGHTS = env_json(
    "LOCAL_IMAGE_COMPONENT_WEIGHTS",
    {
        "metadata_score": 0.25,
        "artifact_score": 0.45,
        "frequency_score": 0.30,
    },
)
LOCAL_VIDEO_COMPONENT_WEIGHTS = env_json(
    "LOCAL_VIDEO_COMPONENT_WEIGHTS",
    {
        "frame_mean_score": 0.45,
        "temporal_score": 0.20,
        "metadata_score": 0.15,
        "audio_score": 0.20,
    },
)
DETECTION_PROVIDER_WEIGHTS = env_json(
    "DETECTION_PROVIDER_WEIGHTS",
    {
        "local": 0.45,
        "illuminarty": 0.30,
        "reality_defender": 0.25,
    },
)
DETECTION_LABEL_THRESHOLDS = {
    "low": env_float("DETECTION_LABEL_LOW_THRESHOLD", 0.35),
    "high": env_float("DETECTION_LABEL_HIGH_THRESHOLD", 0.68),
}
if DETECTION_LABEL_THRESHOLDS["high"] <= DETECTION_LABEL_THRESHOLDS["low"]:
    DETECTION_LABEL_THRESHOLDS = {"low": 0.35, "high": 0.68}
LOCAL_ONLY_LABEL_THRESHOLDS = {
    "low": env_float("LOCAL_ONLY_LABEL_LOW_THRESHOLD", 0.46),
    "high": env_float("LOCAL_ONLY_LABEL_HIGH_THRESHOLD", 0.78),
}
if LOCAL_ONLY_LABEL_THRESHOLDS["high"] <= LOCAL_ONLY_LABEL_THRESHOLDS["low"]:
    LOCAL_ONLY_LABEL_THRESHOLDS = {"low": 0.46, "high": 0.78}
AI_DETECTION_LABEL_THRESHOLD = DETECTION_LABEL_THRESHOLDS["high"]
DETECTION_DISAGREEMENT_SPREAD_THRESHOLD = env_float("DETECTION_DISAGREEMENT_SPREAD_THRESHOLD", 0.35)
LOCAL_ONLY_COMPONENT_SPREAD_THRESHOLD = env_float("LOCAL_ONLY_COMPONENT_SPREAD_THRESHOLD", 0.24)

ILLUMINARTY_ENABLED = env_bool("ILLUMINARTY_ENABLED", False)
ILLUMINARTY_API_KEY = os.environ.get("ILLUMINARTY_API_KEY", "").strip()
ILLUMINARTY_API_URL = os.environ.get("ILLUMINARTY_API_URL", "").strip()
ILLUMINARTY_TIMEOUT_SECONDS = env_float("ILLUMINARTY_TIMEOUT_SECONDS", 6.0)
ILLUMINARTY_AUTH_HEADER = os.environ.get("ILLUMINARTY_AUTH_HEADER", "Authorization").strip() or "Authorization"
ILLUMINARTY_AUTH_SCHEME = os.environ.get("ILLUMINARTY_AUTH_SCHEME", "Bearer").strip()
ILLUMINARTY_UPLOAD_FIELD_NAME = os.environ.get("ILLUMINARTY_UPLOAD_FIELD_NAME", "file").strip() or "file"

REALITY_DEFENDER_ENABLED = env_bool("REALITY_DEFENDER_ENABLED", False)
REALITY_DEFENDER_API_KEY = os.environ.get("REALITY_DEFENDER_API_KEY", "").strip()
REALITY_DEFENDER_API_URL = os.environ.get(
    "REALITY_DEFENDER_API_URL",
    "https://api.prd.realitydefender.xyz",
).strip()
REALITY_DEFENDER_TIMEOUT_SECONDS = env_float("REALITY_DEFENDER_TIMEOUT_SECONDS", 6.0)
REALITY_DEFENDER_MAX_POLLS = env_int("REALITY_DEFENDER_MAX_POLLS", 2)
REALITY_DEFENDER_POLL_INTERVAL_SECONDS = env_float("REALITY_DEFENDER_POLL_INTERVAL_SECONDS", 1.0)
REALITY_DEFENDER_SOFT_LIMIT_PER_DAY = env_int("REALITY_DEFENDER_SOFT_LIMIT_PER_DAY", 20)
ENABLE_EXTERNAL_VIDEO_PROVIDERS = env_bool("ENABLE_EXTERNAL_VIDEO_PROVIDERS", False)

# Backward-compatible aliases for older modules that still read the old names.
DETECTION_WEIGHTS = {
    "image": dict(LOCAL_IMAGE_COMPONENT_WEIGHTS),
    "video": {
        "frame_mean_score": LOCAL_VIDEO_COMPONENT_WEIGHTS.get("frame_mean_score", 0.45),
        "temporal_score": LOCAL_VIDEO_COMPONENT_WEIGHTS.get("temporal_score", 0.20),
        "metadata_score": LOCAL_VIDEO_COMPONENT_WEIGHTS.get("metadata_score", 0.15),
        "audio_score": LOCAL_VIDEO_COMPONENT_WEIGHTS.get("audio_score", 0.20),
    },
}


REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "detection_burst": "10/hour",
        "detection_sustained": "30/day",
        "results": "120/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}
