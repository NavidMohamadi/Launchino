"""Single env-var admin account -- not a full admin-management system.

See api/config.py's ADMIN_EMAIL/ADMIN_PASSWORD_HASH and PROJECT_NOTES.md.
There is no admin table and no registration endpoint; the one admin identity
is fixed at deploy/config time.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.auth import ADMIN_TOKEN_EXPIRY, create_access_token, verify_password
from api.config import ADMIN_EMAIL, ADMIN_PASSWORD_HASH
from api.models_api import AdminAuthResponse, AdminLoginRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=AdminAuthResponse)
def login_admin(payload: AdminLoginRequest) -> AdminAuthResponse:
    if (
        not ADMIN_EMAIL or not ADMIN_PASSWORD_HASH
        or payload.email.lower() != ADMIN_EMAIL.lower()
        or not verify_password(payload.password, ADMIN_PASSWORD_HASH)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(subject="admin", role="admin", expires_delta=ADMIN_TOKEN_EXPIRY)
    return AdminAuthResponse(access_token=token)
