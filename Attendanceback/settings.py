from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------------
# SECURITY
# -----------------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "*",
    ".onrender.com",
    "127.0.0.1",
    "localhost",
]

# -----------------------------------------------------------------------------------
# APPS
# -----------------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'Attendanceapp',

    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

# -----------------------------------------------------------------------------------
# MIDDLEWARE
# -----------------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "Attendanceapp.middleware.BlockStatusMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "Attendanceapp.middleware.DisableCachingMiddleware",
]

# -----------------------------------------------------------------------------------
# URL / WSGI
# -----------------------------------------------------------------------------------
ROOT_URLCONF = 'Attendanceback.urls'
WSGI_APPLICATION = 'Attendanceback.wsgi.application'

# -----------------------------------------------------------------------------------
# TEMPLATES
# -----------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "Attendanceapp.context_processors.pending_counts",
            ],
        },
    },
]

# -----------------------------------------------------------------------------------
# DATABASE (SUPABASE ONLY)
# -----------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres.nmzwqxymwxevtscedvpc",
        "PASSWORD": "Saikumar2708",
        "HOST": "aws-1-ap-southeast-2.pooler.supabase.com",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "sslmode": "require",
            "connect_timeout": 10,
        },
    }
}

# -----------------------------------------------------------------------------------
# CUSTOM USER MODEL
# -----------------------------------------------------------------------------------
AUTH_USER_MODEL = "Attendanceapp.User"

# -----------------------------------------------------------------------------------
# PASSWORD VALIDATORS
# -----------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------------------------------------------------
# INTERNATIONALIZATION
# -----------------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = False

# -----------------------------------------------------------------------------------
# STATIC FILES (Render)
# -----------------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# -----------------------------------------------------------------------------------
# REST FRAMEWORK
# -----------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "Attendanceapp.authentication.UserSessionAuthentication",
    ),
}

# -----------------------------------------------------------------------------------
# CORS + CSRF
# -----------------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://*.onrender.com",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------------
# GEO-FENCE SETTINGS
# Open https://maps.app.goo.gl/tPShGypWLgSoiEpm8 in your browser,
# look at the URL bar for @lat,lng and fill in the values below.
# -----------------------------------------------------------------------------------
OFFICE_LATITUDE = 8.1631162   # company Technologies, Tirunelveli
OFFICE_LONGITUDE = 77.4108498  # company Technologies, Tirunelveli
GEOFENCE_RADIUS_METERS = 10000  # Increased for local testing

# -----------------------------------------------------------------------------------
# SESSION SETTINGS
# -----------------------------------------------------------------------------------
SESSION_COOKIE_AGE = 90 * 24 * 60 * 60  # 90 Days in seconds
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
