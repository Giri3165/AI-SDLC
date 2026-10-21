import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-this-in-production")

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "ai_sdlc")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "no-reply@ai-sdlc.local")

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    # Used by standalone scripts (like send_weekly_digest.py) to build
    # absolute links, since there's no incoming HTTP request there for
    # url_for(..., _external=True) to infer the host from.
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000")
