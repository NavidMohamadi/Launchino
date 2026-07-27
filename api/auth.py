"""Password hashing, JWT issuance/validation, and FastAPI auth dependencies.

Three roles: "candidate" (subject = talent_id), "company" (subject =
company_id), "admin" (subject = the fixed string "admin" -- see
api/config.py's ADMIN_EMAIL/ADMIN_PASSWORD_HASH, a single env-var account,
not a full admin-management system).

No refresh-token flow (see PROJECT_NOTES.md) -- a token simply expires and
the caller logs in again.
"""

from __future__ import annotations

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from api.config import JWT_ALGORITHM, JWT_SECRET_KEY

CANDIDATE_TOKEN_EXPIRY = timedelta(hours=24)
COMPANY_TOKEN_EXPIRY = timedelta(hours=24)
ADMIN_TOKEN_EXPIRY = timedelta(hours=4)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, subject: str, role: str, expires_delta: timedelta) -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured -- refusing to sign a forgeable token")
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    if not JWT_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Auth is not configured (JWT_SECRET_KEY missing)")
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired -- please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_claims(authorization: Optional[str] = Header(None)) -> dict:
    """Extracts and validates the bearer token. Any authenticated caller reaches
    this; per-route dependencies below narrow it down to the right role(s)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[len("Bearer "):]
    return _decode_token(token)


def require_role(*roles: str):
    """Dependency factory: 403s unless the caller's role is one of `roles`.

    Route handlers still perform their own ownership check (e.g. "is this
    candidate's own talent_id") against the returned claims -- this only
    narrows by role, not by which specific record the caller may touch.
    """

    def dependency(claims: dict = Depends(get_current_claims)) -> dict:
        if claims.get("role") not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of roles {roles}")
        return claims

    return dependency


def require_candidate_self_or_admin(talent_id: UUID, claims: dict = Depends(require_role("candidate", "admin"))) -> dict:
    """Shared ownership check for candidate-scoped routes: the token must
    belong to this exact talent_id, or be an admin token."""
    if claims["role"] == "candidate" and claims["sub"] != str(talent_id):
        raise HTTPException(status_code=403, detail="Cannot access another candidate's record")
    return claims


def require_company_self_or_admin(company_id: UUID, claims: dict = Depends(require_role("company", "admin"))) -> dict:
    """Shared ownership check for company-scoped routes: the token must
    belong to this exact company_id, or be an admin token."""
    if claims["role"] == "company" and claims["sub"] != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot access another company's record")
    return claims


def check_vacancy_ownership(claims: dict, vacancy_company_id: Optional[UUID]) -> None:
    """Manual ownership check for vacancy-scoped routes -- not a Depends() factory,
    because the thing being checked against (the vacancy's real company_id) can
    only be known after a DB lookup keyed by the vacancy_id path param, which
    every route calling this already does for its own "does this vacancy exist"
    check. Call this right after that lookup, passing the row/profile's
    company_id.

    vacancy_company_id is None for vacancies created before company auth
    existed (see PROJECT_NOTES.md) -- those are admin-only until manually
    assigned a real owner; no company token can claim them.
    """
    if claims["role"] == "admin":
        return
    if vacancy_company_id is None or claims["sub"] != str(vacancy_company_id):
        raise HTTPException(status_code=403, detail="Cannot access a vacancy you don't own")
