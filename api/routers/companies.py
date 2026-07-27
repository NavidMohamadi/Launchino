from __future__ import annotations

import uuid

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import (
    COMPANY_TOKEN_EXPIRY, create_access_token, hash_password, require_company_self_or_admin, verify_password,
)
from api.database import get_connection
from api.models_api import CONSENT_POLICY_VERSION, CompanyAuthResponse, CompanyCreate, CompanyLoginRequest, CompanyOut
from api.rate_limit import limiter

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", response_model=CompanyAuthResponse, status_code=201)
@limiter.limit("5/hour")
def create_company(
    request: Request, payload: CompanyCreate, conn: Connection = Depends(get_connection),
) -> CompanyAuthResponse:
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
                last_login_at, career_page_url, country_code, kvk_number, consent_at, consent_version
            ) values (
                :company_id, :legal_name, :display_name, :website_domain, :contact_email, :password_hash,
                now(), :career_page_url, :country_code, :kvk_number, now(), :consent_version
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
            "consent_version": CONSENT_POLICY_VERSION,
        },
    )
    company = CompanyOut(
        company_id=company_id, legal_name=payload.legal_name, display_name=payload.display_name,
        website_domain=payload.website_domain, contact_email=payload.contact_email,
    )
    token = create_access_token(subject=str(company_id), role="company", expires_delta=COMPANY_TOKEN_EXPIRY)
    return CompanyAuthResponse(access_token=token, company=company)


@router.post("/login", response_model=CompanyAuthResponse)
@limiter.limit("10/minute")
def login_company(
    request: Request, payload: CompanyLoginRequest, conn: Connection = Depends(get_connection),
) -> CompanyAuthResponse:
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


@router.get("/{company_id}/export")
def export_company_data(
    company_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_company_self_or_admin),
) -> dict:
    """GDPR data-export mechanism, mirroring GET /candidates/{id}/export."""
    company_row = conn.execute(
        text(
            "select company_id, legal_name, display_name, website_domain, contact_email, career_page_url, "
            "country_code, kvk_number, consent_at, consent_version, last_login_at, created_at, updated_at "
            "from company where company_id = :company_id"
        ),
        {"company_id": str(company_id)},
    ).mappings().first()
    if not company_row:
        raise HTTPException(status_code=404, detail="Company not found")

    vacancies = conn.execute(
        text(
            "select vacancy_id, role_title, lifecycle_status, created_at from vacancy "
            "where company_id = :company_id order by created_at desc"
        ),
        {"company_id": str(company_id)},
    ).mappings().all()

    match_history = conn.execute(
        text(
            """
            select mr.match_run_id, mr.vacancy_id, mr.algorithm_version, mr.created_at
            from match_run mr join vacancy v on v.vacancy_id = mr.vacancy_id
            where v.company_id = :company_id order by mr.created_at desc
            """
        ),
        {"company_id": str(company_id)},
    ).mappings().all()

    ai_usage = conn.execute(
        text(
            """
            select usage_id, occurred_at, task, model, input_tokens, output_tokens, estimated_cost_usd, success
            from ai_usage_log where vacancy_id in (select vacancy_id from vacancy where company_id = :company_id)
            order by occurred_at
            """
        ),
        {"company_id": str(company_id)},
    ).mappings().all()

    def _row(r: dict) -> dict:
        return {k: (v.isoformat() if hasattr(v, "isoformat") else (str(v) if isinstance(v, UUID) else v)) for k, v in dict(r).items()}

    return {
        "profile": _row(company_row),
        "vacancies": [_row(r) for r in vacancies],
        "match_history": [_row(r) for r in match_history],
        "ai_usage_log": [_row(r) for r in ai_usage],
    }


@router.delete("/{company_id}")
def delete_company(
    company_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_company_self_or_admin),
) -> dict:
    """GDPR erasure mechanism, mirroring DELETE /candidates/{id} -- see that
    endpoint's docstring for the full design-decision writeup (flagged for
    the user's/legal review, not silently decided).

    Companies aren't natural persons under GDPR, but contact_email is
    personal data of whoever holds that inbox -- this clears the directly
    identifying contact/login fields. legal_name/display_name are kept: they
    are the company's own registered business identity (already public on
    every vacancy posting), not personal data of an individual, and vacancies
    posted by this company are left untouched -- they're the platform's
    ongoing job-discovery data for candidates who may have been matched
    against them, not this account's personal data to unilaterally erase.
    """
    company_row = conn.execute(
        text("select 1 from company where company_id = :company_id"), {"company_id": str(company_id)}
    ).first()
    if not company_row:
        raise HTTPException(status_code=404, detail="Company not found")

    conn.execute(
        text(
            """
            update company set
                contact_email = :tombstone_email,
                password_hash = null,
                active = false,
                updated_at = now()
            where company_id = :company_id
            """
        ),
        {"company_id": str(company_id), "tombstone_email": f"deleted-{company_id}@deleted.invalid"},
    )
    return {"company_id": company_id, "status": "deleted"}
