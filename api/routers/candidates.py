from __future__ import annotations

import json
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.ai_client import AIExtractionError
from api.auth import (
    CANDIDATE_TOKEN_EXPIRY, create_access_token, hash_password, require_candidate_self_or_admin, require_role,
    verify_password,
)
from api.database import get_connection
from api.extraction_service import run_cv_extraction
from api.matching_service import load_dictionary
from api.models_api import (
    CONSENT_POLICY_VERSION, CandidateAuthResponse, CandidateLoginRequest, CandidateSurveySubmission,
    CVExtractionRequest, SubscriptionUpdateRequest, TalentCreate, TalentOut,
)
from api.rate_limit import limiter
from candidate_extraction import CandidateExtractionResult
from schemas import Talent, TalentElementValue

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("", response_model=CandidateAuthResponse, status_code=201)
@limiter.limit("5/hour")
def create_candidate(
    request: Request, payload: TalentCreate, conn: Connection = Depends(get_connection),
) -> CandidateAuthResponse:
    existing = conn.execute(
        text("select talent_id from talent where email = :email"), {"email": payload.email}
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A candidate with this email is already registered")
    talent_id = uuid.uuid4()

    # Reuses src/schemas.py's own Talent model (e.g. its timezone-aware
    # timestamp rule) instead of re-deriving that validation here.
    try:
        Talent(
            talent_id=str(talent_id), full_name=payload.full_name, email=payload.email,
            job_discovery_subscription=payload.job_discovery_subscription,
            subscription_expires_at=payload.subscription_expires_at,
            job_discovery_campaign_opt_in=payload.job_discovery_campaign_opt_in,
            subscription_updated_at=payload.subscription_updated_at,
            subscription_source=payload.subscription_source,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    conn.execute(
        text(
            """
            insert into talent (
                talent_id, full_name, email, password_hash, last_login_at, job_discovery_subscription,
                subscription_expires_at, job_discovery_campaign_opt_in, subscription_updated_at, subscription_source,
                consent_at, consent_version
            ) values (
                :talent_id, :full_name, :email, :password_hash, now(), :job_discovery_subscription,
                :subscription_expires_at, :job_discovery_campaign_opt_in, :subscription_updated_at, :subscription_source,
                now(), :consent_version
            )
            """
        ),
        {
            "talent_id": str(talent_id),
            "full_name": payload.full_name,
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "job_discovery_subscription": payload.job_discovery_subscription.value,
            "subscription_expires_at": payload.subscription_expires_at,
            "job_discovery_campaign_opt_in": payload.job_discovery_campaign_opt_in,
            "subscription_updated_at": payload.subscription_updated_at,
            "subscription_source": payload.subscription_source.value if payload.subscription_source else None,
            "consent_version": CONSENT_POLICY_VERSION,
        },
    )
    candidate = TalentOut(
        talent_id=talent_id, full_name=payload.full_name, email=payload.email, profile_status="registered",
        job_discovery_subscription=payload.job_discovery_subscription,
        subscription_expires_at=payload.subscription_expires_at,
        job_discovery_campaign_opt_in=payload.job_discovery_campaign_opt_in,
        subscription_updated_at=payload.subscription_updated_at,
        subscription_source=payload.subscription_source,
    )
    token = create_access_token(subject=str(talent_id), role="candidate", expires_delta=CANDIDATE_TOKEN_EXPIRY)
    return CandidateAuthResponse(access_token=token, candidate=candidate)


@router.post("/login", response_model=CandidateAuthResponse)
@limiter.limit("10/minute")
def login_candidate(
    request: Request, payload: CandidateLoginRequest, conn: Connection = Depends(get_connection),
) -> CandidateAuthResponse:
    row = conn.execute(
        text("select * from talent where email = :email"), {"email": payload.email}
    ).mappings().first()
    if not row or not verify_password(payload.password, row["password_hash"] or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    conn.execute(
        text("update talent set last_login_at = now() where talent_id = :talent_id"),
        {"talent_id": row["talent_id"]},
    )
    candidate = TalentOut(**dict(row))
    token = create_access_token(subject=str(row["talent_id"]), role="candidate", expires_delta=CANDIDATE_TOKEN_EXPIRY)
    return CandidateAuthResponse(access_token=token, candidate=candidate)


@router.get("/{talent_id}", response_model=TalentOut)
def get_candidate(
    talent_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_candidate_self_or_admin),
) -> TalentOut:
    row = conn.execute(
        text("select * from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return TalentOut(**dict(row))


@router.patch("/{talent_id}/subscription", response_model=TalentOut)
def update_candidate_subscription(
    talent_id: UUID, payload: SubscriptionUpdateRequest, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("admin")),
) -> TalentOut:
    # ADMIN-ONLY: requires a valid admin JWT (api/auth.py's require_role("admin")).
    # Previously wide open with no auth at all -- see PROJECT_NOTES.md's now-resolved
    # entry on this. Still exists purely for manual testing of the job discovery
    # entitlement gate until real billing exists.
    row = conn.execute(
        text("select 1 from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    try:
        Talent(
            talent_id=str(talent_id), full_name="placeholder", email="placeholder@example.com",
            job_discovery_subscription=payload.job_discovery_subscription,
            subscription_expires_at=payload.subscription_expires_at,
            subscription_source=payload.subscription_source,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    conn.execute(
        text(
            """
            update talent set
                job_discovery_subscription = :job_discovery_subscription,
                subscription_expires_at = :subscription_expires_at,
                subscription_source = :subscription_source,
                subscription_updated_at = now()
            where talent_id = :talent_id
            """
        ),
        {
            "talent_id": str(talent_id),
            "job_discovery_subscription": payload.job_discovery_subscription.value,
            "subscription_expires_at": payload.subscription_expires_at,
            "subscription_source": payload.subscription_source.value if payload.subscription_source else None,
        },
    )
    updated = conn.execute(
        text("select * from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).mappings().first()
    return TalentOut(**dict(updated))


@router.post("/{talent_id}/survey", status_code=201)
def submit_candidate_survey(
    talent_id: UUID, payload: CandidateSurveySubmission, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_candidate_self_or_admin),
) -> dict:
    talent_row = conn.execute(
        text("select 1 from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).first()
    if not talent_row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    known_elements = {r[0] for r in conn.execute(text("select element_id from fit_element")).all()}

    stored = 0
    for item in payload.values:
        if item.element_id not in known_elements:
            raise HTTPException(status_code=400, detail=f"Unknown element_id: {item.element_id}")

        # Reuses src/schemas.py's own consistency rules (ANSWERED/UNKNOWN/NOT_SCORED
        # reason pairing, non-empty ANSWERED payload) instead of re-deriving them.
        try:
            TalentElementValue(
                talent_id=str(talent_id), element_id=item.element_id, value=item.value,
                value_status=item.value_status, unknown_reason=item.unknown_reason,
                not_scored_reason=item.not_scored_reason, source_type=item.source_type,
                last_confirmed_at=item.last_confirmed_at,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"{item.element_id}: {exc.errors()}") from exc

        next_version = conn.execute(
            text(
                "select coalesce(max(record_version), 0) + 1 from talent_element_value "
                "where talent_id = :talent_id and element_id = :element_id"
            ),
            {"talent_id": str(talent_id), "element_id": item.element_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                insert into talent_element_value (
                    talent_id, element_id, value, value_status, unknown_reason, not_scored_reason,
                    source_type, last_confirmed_at, shareable_with_employer, record_version
                ) values (
                    :talent_id, :element_id, cast(:value as jsonb), :value_status, :unknown_reason,
                    :not_scored_reason, :source_type, :last_confirmed_at, :shareable_with_employer,
                    :record_version
                )
                """
            ),
            {
                "talent_id": str(talent_id),
                "element_id": item.element_id,
                "value": json.dumps(item.value),
                "value_status": item.value_status.value,
                "unknown_reason": item.unknown_reason.value if item.unknown_reason else None,
                "not_scored_reason": item.not_scored_reason.value if item.not_scored_reason else None,
                "source_type": item.source_type.value,
                "last_confirmed_at": item.last_confirmed_at,
                "shareable_with_employer": item.shareable_with_employer,
                "record_version": next_version,
            },
        )
        stored += 1
    return {"talent_id": talent_id, "values_stored": stored}


@router.post("/{talent_id}/extract-cv", response_model=CandidateExtractionResult)
@limiter.limit("20/hour")
def extract_cv(
    request: Request, talent_id: UUID, payload: CVExtractionRequest, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_candidate_self_or_admin),
) -> CandidateExtractionResult:
    """Extract CAP/TASK elements from raw CV text via Claude; never persists.

    Returns a draft the caller reviews/edits before resubmitting the relevant
    items through POST /candidates/{talent_id}/survey, which is the only
    place talent_element_value actually gets written.
    """
    talent_row = conn.execute(
        text("select 1 from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).first()
    if not talent_row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    dictionary = load_dictionary(conn)
    try:
        return run_cv_extraction(candidate_id=str(talent_id), cv_text=payload.cv_text, dictionary=dictionary)
    except AIExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{talent_id}/export")
def export_candidate_data(
    talent_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_candidate_self_or_admin),
) -> dict:
    """GDPR data-export mechanism: every piece of personal data held about
    this candidate, in one response. Self-or-admin only (same ownership rule
    as every other candidate-scoped route)."""
    talent_row = conn.execute(
        text(
            "select talent_id, full_name, email, profile_status, job_discovery_subscription, "
            "subscription_expires_at, job_discovery_campaign_opt_in, subscription_source, "
            "consent_at, consent_version, last_login_at, created_at, updated_at "
            "from talent where talent_id = :talent_id"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().first()
    if not talent_row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    survey_answers = conn.execute(
        text(
            "select element_id, value, value_status, unknown_reason, not_scored_reason, source_type, "
            "last_confirmed_at, shareable_with_employer, record_version, created_at "
            "from talent_element_value where talent_id = :talent_id order by element_id, record_version"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    evidence = conn.execute(
        text(
            "select evidence_id, element_id, source_type, description, quality, observed_at, "
            "shareable_with_employer, created_at from talent_evidence where talent_id = :talent_id"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    match_history = conn.execute(
        text(
            """
            select ms.match_run_id, mr.vacancy_id, mr.algorithm_version, ms.overall_score,
                   ms.overall_coverage, ms.result_lane, mr.created_at
            from match_summary ms join match_run mr on mr.match_run_id = ms.match_run_id
            where ms.talent_id = :talent_id order by mr.created_at desc
            """
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    recommendations = conn.execute(
        text(
            "select recommendation_id, vacancy_id, result_lane, overall_score, overall_coverage, "
            "generated_at from job_recommendation where talent_id = :talent_id order by generated_at desc"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    ai_usage = conn.execute(
        text(
            "select usage_id, occurred_at, task, model, input_tokens, output_tokens, "
            "estimated_cost_usd, success from ai_usage_log where talent_id = :talent_id order by occurred_at"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    def _row(r: dict) -> dict:
        return {k: (v.isoformat() if hasattr(v, "isoformat") else (str(v) if isinstance(v, UUID) else v)) for k, v in dict(r).items()}

    return {
        "profile": _row(talent_row),
        "survey_answers": [_row(r) for r in survey_answers],
        "evidence": [_row(r) for r in evidence],
        "match_history": [_row(r) for r in match_history],
        "job_recommendations": [_row(r) for r in recommendations],
        "ai_usage_log": [_row(r) for r in ai_usage],
    }


@router.delete("/{talent_id}")
def delete_candidate(
    talent_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_candidate_self_or_admin),
) -> dict:
    """GDPR erasure mechanism.

    DESIGN DECISION (flagged, not silently made -- see PROJECT_NOTES.md and
    the security-hardening task this was built under): this anonymizes the
    talent row rather than issuing a hard DELETE. A true row delete would
    violate foreign-key constraints from every table that references
    talent_id (talent_element_value, talent_evidence, match_item_result,
    match_summary, job_recommendation, preliminary_opportunity_signal,
    human_review, ai_usage_log) unless those were cascade-deleted too --
    which would also destroy a company's own legitimate record of "we ran a
    match against some candidate" / "we received this recommendation," data
    that isn't solely this candidate's to unilaterally erase.

    What this actually does:
      - full_name/email are replaced with a non-identifying tombstone value,
        password_hash is cleared (the account can never log in again).
      - talent_evidence and talent_element_value rows (the candidate's own
        free-text survey content) are hard-deleted outright -- nothing else
        references these rows, so there's no FK/retention reason to keep them.
      - match_run/match_summary/job_recommendation/ai_usage_log rows that
        reference this talent_id are left in place, but they no longer
        resolve to an identifiable person once the profile above is
        anonymized -- they become anonymous aggregate/business records.

    This is a considered default, not a rubber-stamped assumption -- flagged
    explicitly to the user for their own (and likely legal) review, since
    "what does erasure mean when data is shared with a third party" is a
    real legal judgment call, not an engineering one.
    """
    talent_row = conn.execute(
        text("select 1 from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).first()
    if not talent_row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    conn.execute(text("delete from talent_evidence where talent_id = :talent_id"), {"talent_id": str(talent_id)})
    conn.execute(text("delete from talent_element_value where talent_id = :talent_id"), {"talent_id": str(talent_id)})
    conn.execute(
        text(
            """
            update talent set
                full_name = 'Deleted user',
                email = :tombstone_email,
                password_hash = null,
                profile_status = 'deleted',
                updated_at = now()
            where talent_id = :talent_id
            """
        ),
        {"talent_id": str(talent_id), "tombstone_email": f"deleted-{talent_id}@deleted.invalid"},
    )
    return {"talent_id": talent_id, "status": "deleted"}
