from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import COMPANY_TOKEN_EXPIRY, create_access_token, hash_password, verify_password
from api.database import get_connection
from api.models_api import CompanyAuthResponse, CompanyCreate, CompanyLoginRequest, CompanyOut

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", response_model=CompanyAuthResponse, status_code=201)
def create_company(payload: CompanyCreate, conn: Connection = Depends(get_connection)) -> CompanyAuthResponse:
    existing = conn.execute(
        text(
            "select 1 from company where lower(website_domain) = lower(:domain) "
            "or lower(contact_email) = lower(:email)"
        ),
        {"domain": payload.website_domain, "email": payload.contact_email},
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A company with this domain or contact email is already registered")

    company_id = uuid.uuid4()
    conn.execute(
        text(
            """
            insert into company (
                company_id, legal_name, display_name, website_domain, contact_email, password_hash,
                last_login_at, career_page_url, country_code, kvk_number
            ) values (
                :company_id, :legal_name, :display_name, :website_domain, :contact_email, :password_hash,
                now(), :career_page_url, :country_code, :kvk_number
            )
            """
        ),
        {
            "company_id": str(company_id),
            "legal_name": payload.legal_name,
            "display_name": payload.display_name,
            "website_domain": payload.website_domain,
            "contact_email": payload.contact_email,
            "password_hash": hash_password(payload.password),
            "career_page_url": payload.career_page_url,
            "country_code": payload.country_code,
            "kvk_number": payload.kvk_number,
        },
    )
    company = CompanyOut(
        company_id=company_id, legal_name=payload.legal_name, display_name=payload.display_name,
        website_domain=payload.website_domain, contact_email=payload.contact_email,
    )
    token = create_access_token(subject=str(company_id), role="company", expires_delta=COMPANY_TOKEN_EXPIRY)
    return CompanyAuthResponse(access_token=token, company=company)


@router.post("/login", response_model=CompanyAuthResponse)
def login_company(payload: CompanyLoginRequest, conn: Connection = Depends(get_connection)) -> CompanyAuthResponse:
    row = conn.execute(
        text("select * from company where lower(contact_email) = lower(:email)"), {"email": payload.email}
    ).mappings().first()
    if not row or not verify_password(payload.password, row["password_hash"] or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    conn.execute(
        text("update company set last_login_at = now() where company_id = :company_id"),
        {"company_id": row["company_id"]},
    )
    company = CompanyOut(
        company_id=row["company_id"], legal_name=row["legal_name"], display_name=row["display_name"],
        website_domain=row["website_domain"], contact_email=row["contact_email"],
    )
    token = create_access_token(subject=str(row["company_id"]), role="company", expires_delta=COMPANY_TOKEN_EXPIRY)
    return CompanyAuthResponse(access_token=token, company=company)
