import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())

DEBUG = os.environ.get("DEBUG", "0").lower() in ("1", "true")

SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-insecure-key" if DEBUG else "")
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")

for name in ("SECRET_KEY", "TOMTOM_API_KEY"):
    if not globals()[name]:
        raise ImproperlyConfigured(f"{name} environment variable is required")

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

INSTALLED_APPS = ["rest_framework", "trips"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {}

# The built React app is served from the site root by WhiteNoise (index.html for "/").
STATIC_URL = "static/"
WHITENOISE_ROOT = BASE_DIR.parent / "frontend" / "dist"
WHITENOISE_INDEX_FILE = True
WHITENOISE_IMMUTABLE_FILE_TEST = lambda path, url: url.startswith("/assets/")  # Vite hashed bundles

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "OPTIONS": {"MAX_ENTRIES": 20000}}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"trip": "15/min", "geocode": "120/min"},
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_TZ = True
TIME_ZONE = "UTC"
