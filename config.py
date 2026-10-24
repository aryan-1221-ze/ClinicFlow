"""Application configuration. All secrets come from environment variables."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # python-dotenv is optional; real environment variables always win.
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def _flag(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # If SECRET_KEY is not set a random one is generated for this process only.
    # Sessions (and CSRF tokens) then reset on every restart.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_IS_TEMPORARY = not os.environ.get("SECRET_KEY")

    DATABASE_PATH = os.environ.get("DATABASE_PATH") or str(BASE_DIR / "database" / "clinicflow.db")
    AUTO_SEED = _flag("AUTO_SEED", True)

    # Whole-request limit enforced by Flask (returns HTTP 413 when exceeded).
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", 1_048_576))
    MAX_CSV_ROWS = int(os.environ.get("MAX_CSV_ROWS", 5000))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", False)

    PER_PAGE = 15
