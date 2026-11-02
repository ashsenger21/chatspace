"""
config.py - Application Configuration

Supports both local development (SQLite) and production (PostgreSQL + Cloudinary).
All sensitive values are read from environment variables.
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # -----------------------------------------------------------------------
    # SECRET KEY
    # -----------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "chatspace-dev-secret-change-in-production")

    # -----------------------------------------------------------------------
    # DATABASE
    # Render provides DATABASE_URL as a PostgreSQL URL (postgres://...).
    # SQLAlchemy needs postgresql:// instead of postgres://, so we fix that.
    # Falls back to local SQLite for development.
    # -----------------------------------------------------------------------
    _db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}")
    # Fix Render's legacy "postgres://" prefix
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # -----------------------------------------------------------------------
    # CLOUDINARY (cloud file storage for images, videos, audio)
    # Sign up free at https://cloudinary.com and copy these three values.
    # -----------------------------------------------------------------------
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY    = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

    # Whether Cloudinary is configured (both local and production check this)
    USE_CLOUDINARY = bool(
        os.environ.get("CLOUDINARY_CLOUD_NAME") and
        os.environ.get("CLOUDINARY_API_KEY") and
        os.environ.get("CLOUDINARY_API_SECRET")
    )

    # -----------------------------------------------------------------------
    # LOCAL FILE UPLOADS (fallback when Cloudinary is NOT configured)
    # -----------------------------------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
    ALLOWED_AUDIO_EXTENSIONS = {"webm", "ogg", "mp3", "wav", "m4a"}

    # -----------------------------------------------------------------------
    # FLASK-SOCKETIO
    # Use "eventlet" in production for better WebSocket performance.
    # -----------------------------------------------------------------------
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "eventlet")

    # -----------------------------------------------------------------------
    # SESSION / SECURITY
    # -----------------------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Use secure cookies in production (HTTPS only)
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
