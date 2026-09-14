"""
Configuration Django — Plateforme de prévision du taux d'engagement des AE (DGB/MINFI).

Tous les secrets (SECRET_KEY, mots de passe BDD, identifiants Google) sont lus
depuis des variables d'environnement (.env), jamais codés en dur.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ==================================================
# SÉCURITÉ
# ==================================================
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    # Ne jamais utiliser cette clé en production — elle est générée à la
    # volée uniquement pour permettre à `manage.py check`/tests de tourner
    # si le développeur a oublié de créer son .env.
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()

DEBUG = env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", default=False)

# ==================================================
# APPLICATIONS
# ==================================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Auth Google (allauth)
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "widget_tweaks",
    # Apps du projet
    "accounts",
    "core",
    "dashboard",
    "datasets",
    "forecasting",
    "predictions",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "core.middleware.JournalActiviteMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ==================================================
# BASE DE DONNÉES — PostgreSQL (variables d'environnement)
# ==================================================
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "dgb_ae_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
# NB : si DB_ENGINE=django.db.backends.sqlite3, NAME est utilisé comme chemin
# de fichier — pratique pour du développement local sans serveur PostgreSQL.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["NAME"] = BASE_DIR / os.environ.get("DB_NAME", "db.sqlite3")
    DATABASES["default"].pop("USER", None)
    DATABASES["default"].pop("PASSWORD", None)
    DATABASES["default"].pop("HOST", None)
    DATABASES["default"].pop("PORT", None)

AUTH_USER_MODEL = "accounts.Utilisateur"

# ==================================================
# VALIDATION DES MOTS DE PASSE
# ==================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 9}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# ==================================================
# INTERNATIONALISATION — Français (défaut) / Anglais
# ==================================================
from django.utils.translation import gettext_lazy as _  # noqa: E402

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("fr", _("Français")),
    ("en", _("English")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

# ==================================================
# FICHIERS STATIQUES ET MÉDIAS
# ==================================================
STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },

}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Upload de fichiers : limites de sécurité (imports CSV du dataset)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 Mo
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = [".csv"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# AUTHENTIFICATION / REDIRECTIONS
# ==================================================
LOGIN_URL = "accounts:connexion"
LOGIN_REDIRECT_URL = "dashboard:redirection_role"
LOGOUT_REDIRECT_URL = "core:accueil"

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            "secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
    }
}

# ==================================================
# EMAIL (mot de passe oublié)
# ==================================================
if os.environ.get("EMAIL_HOST_USER"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
else:
    # En développement, les emails sont affichés dans la console au lieu d'être envoyés.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "DGB - MINFI <no-reply@minfi.gov.cm>")

# ==================================================
# ASSISTANT IA (Anthropic) — interprétation des prévisions pour le décideur
# ==================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# Nombre maximal de questions autorisées par utilisateur et par heure
# (chaque appel a un coût réel — protège contre l'abus involontaire ou malveillant).
ASSISTANT_IA_LIMITE_PAR_HEURE = int(os.environ.get("ASSISTANT_IA_LIMITE_PAR_HEURE", "20"))

# ==================================================
# LOGGING — jamais de traceback affiché à l'utilisateur, tout est loggé ici
# ==================================================
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "application.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "forecasting": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "datasets": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# ==================================================
# GESTION DES ERREURS PERSONNALISÉES
# ==================================================
handler403 = "core.views.erreur_403"
handler404 = "core.views.erreur_404"
handler500 = "core.views.erreur_500"

# ==================================================
# MESSAGES (Bootstrap 5 alert classes)
# ==================================================
from django.contrib.messages import constants as messages_constants  # noqa: E402

MESSAGE_TAGS = {
    messages_constants.DEBUG: "secondary",
    messages_constants.INFO: "info",
    messages_constants.SUCCESS: "success",
    messages_constants.WARNING: "warning",
    messages_constants.ERROR: "danger",
}
