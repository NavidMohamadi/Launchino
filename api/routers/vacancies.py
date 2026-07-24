from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.ai_client import AIExtractionError
from api.auth import check_vacancy_ownership, require_role
from api.database import get_connection
from api.extraction_service import run_vacancy_extraction
from api.matching_service import load_dictionary
from api.models_api import VacancyCreate, VacancyDescriptionExtractionRequest, VacancyWorkshopSubmission
from api.vacancy_store import fetch_vacancy, insert_vacancy
from company_intake import canonicalise_company_submission
from schemas import VacancyElementValue
from source_schemas import CanonicalVacancyProfile, VerificationStatus
from vacancy_extraction import VacancyExtractionResult

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


@router.post("", response_model=CanonicalVacancyProfile, status_code=201)
def create_vacancy(
    payload: VacancyCreate, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("company")),
) -> CanonicalVacancyProfile:
    # company_id comes from the authenticated token, never the request body
    # (see VacancyCreate's docstring) -- company_exists() is no longer needed
    # since a valid company token guarantees the company row exists.
    company_id = claims["sub"]

    submission = {
        "company_name": payload.company_name,
        "company_domain": payload.company_domain,
        "title": payload.title,
        "description_text": payload.description_text,
        "location_text": payload.location_text,
        "department": payload.department,
        "employment_types": payload.employment_types,
        "work_mode": payload.work_mode,
        "apply_url": payload.apply_url,
        "date_posted": payload.date_posted,
        "valid_through": payload.valid_through,
        "salary": payload.salary,
        "source_url": payload.source_url,
        "external_job_id": payload.external_job_id,
    }
    try:
        profile = canonicalise_company_submission(
            submission, company_id=company_id, category_weights=payload.category_weights,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    insert_vacancy(conn, profile)
    return profile


@router.get("/{vacancy_id}", response_model=CanonicalVacancyProfile)
def get_vacancy_endpoint(
    vacancy_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("company", "admin")),
) -> CanonicalVacancyProfile:
    profile = fetch_vacancy(conn, vacancy_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    check_vacancy_ownership(claims, profile.company_id)
    return profile


@router.post("/{vacancy_id}/workshop", status_code=201)
def submit_vacancy_workshop(
    vacancy_id: UUID, payload: VacancyWorkshopSubmission, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("company", "admin")),
) -> dict:
    # TRUST BOUNDARY: every row this endpoint writes is stamped verification_status=
    # company_validated (see the INSERT below). Previously this was asserted, not
    # enforced (see PROJECT_NOTES.md's now-resolved entry) -- now the caller must be
    # authenticated as the owning company (or admin), via check_vacancy_ownership
    # below, so "confirmed by the company" is a real, checked claim rather than a
    # convention any caller got for free.
    vacancy_row = conn.execute(
        text("select company_id from vacancy where vacancy_id = :vacancy_id"), {"vacancy_id": str(vacancy_id)}
    ).mappings().first()
    if not vacancy_row:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    check_vacancy_ownership(claims, vacancy_row["company_id"])

    known_elements = {r[0] for r in conn.execute(text("select element_id from fit_element")).all()}

    stored = 0
    for item in payload.values:
        if item.element_id not in known_elements:
            raise HTTPException(status_code=400, detail=f"Unknown element_id: {item.element_id}")

        try:
            VacancyElementValue(
                vacancy_id=str(vacancy_id), element_id=item.element_id, value=item.value,
                value_status=item.value_status, unknown_reason=item.unknown_reason,
                not_scored_reason=item.not_scored_reason, source_type=item.source_type,
                item_importance=item.item_importance, requirement_type=item.requirement_type,
                trainability_window=item.trainability_window, last_confirmed_at=item.last_confirmed_at,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"{item.element_id}: {exc.errors()}") from exc

        conn.execute(
            text(
                """
                insert into vacancy_element_value (
                    vacancy_id, element_id, value, value_status, unknown_reason, not_scored_reason,
                    source_type, verification_status, item_importance, requirement_type,
                    trainability_window, last_confirmed_at
                ) values (
                    :vacancy_id, :element_id, cast(:value as jsonb), :value_status, :unknown_reason,
                    :not_scored_reason, :source_type, :verification_status, :item_importance,
                    :requirement_type, :trainability_window, :last_confirmed_at
                )
                on conflict (vacancy_id, element_id) do update set
                    value = excluded.value,
                    value_status = excluded.value_status,
                    unknown_reason = excluded.unknown_reason,
                    not_scored_reason = excluded.not_scored_reason,
                    source_type = excluded.source_type,
                    verification_status = excluded.verification_status,
                    item_importance = excluded.item_importance,
                    requirement_type = excluded.requirement_type,
                    trainability_window = excluded.trainability_window,
                    last_confirmed_at = excluded.last_confirmed_at
                """
            ),
            {
                "vacancy_id": str(vacancy_id),
                "element_id": item.element_id,
                "value": json.dumps(item.value),
                "value_status": item.value_status.value,
                "unknown_reason": item.unknown_reason.value if item.unknown_reason else None,
                "not_scored_reason": item.not_scored_reason.value if item.not_scored_reason else None,
                "source_type": item.source_type.value,
                # /workshop is the human/company confirmation gate: whatever drafted the
                # value (typed by hand, or an AI extraction a human reviewed and resubmitted
                # here), a row that reaches this table has been confirmed at company-direct
                # trust. Without this, every row silently defaulted to the DB's lowest tier
                # ('auto_extracted'), which is wrong regardless of extraction ever existing.
                "verification_status": VerificationStatus.COMPANY_VALIDATED.value,
                "item_importance": item.item_importance,
                "requirement_type": item.requirement_type.value,
                "trainability_window": item.trainability_window.value,
                "last_confirmed_at": item.last_confirmed_at,
            },
        )
        stored += 1
    return {"vacancy_id": vacancy_id, "values_stored": stored}


@router.post("/{vacancy_id}/extract-description", response_model=VacancyExtractionResult)
def extract_vacancy_description(
    vacancy_id: UUID, payload: VacancyDescriptionExtractionRequest, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("company", "admin")),
) -> VacancyExtractionResult:
    """Extract Fit Dictionary items from raw vacancy description text via Claude; never persists.

    Returns a draft the caller reviews/edits before resubmitting the relevant
    items through POST /vacancies/{vacancy_id}/workshop, which is the only
    place vacancy_element_value actually gets written.
    """
    vacancy_row = conn.execute(
        text("select company_id from vacancy where vacancy_id = :vacancy_id"), {"vacancy_id": str(vacancy_id)}
    ).mappings().first()
    if not vacancy_row:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    check_vacancy_ownership(claims, vacancy_row["company_id"])

    dictionary = load_dictionary(conn)
    try:
        return run_vacancy_extraction(
            vacancy_id=str(vacancy_id), vacancy_text=payload.description_text, dictionary=dictionary,
        )
    except AIExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
