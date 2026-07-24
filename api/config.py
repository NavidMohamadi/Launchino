from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# No default -- a missing DATABASE_URL should fail loudly (see JWT_SECRET_KEY
# below for the same reasoning) rather than silently fall back to a bogus
# local connection string in a publicly deployed app.
_RAW_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _with_psycopg_driver(url: str) -> str:
    """SQLAlchemy defaults bare postgresql:// / postgres:// URLs to psycopg2,
    which this project does not install; force the psycopg (3) driver instead."""
    if url.startswith("postgresql+") or url.startswith("postgres+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


DATABASE_URL = _with_psycopg_driver(_RAW_DATABASE_URL)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Auth (see api/auth.py). JWT_SECRET_KEY has no default -- signing tokens with a
# blank/well-known key would make every issued token forgeable, so a missing key
# should fail loudly (api/auth.py raises) rather than silently run insecure.
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"

# Single env-var admin account (see PROJECT_NOTES.md / the auth task) -- not a
# full admin-management system. ADMIN_PASSWORD_HASH is a bcrypt hash, generated
# once and pasted into .env; the plaintext password is never stored anywhere.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
