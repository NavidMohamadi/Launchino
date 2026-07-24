"""Admin-only review queue endpoints (Phase 2 of the admin dashboard).

Reuses the existing admin auth (api/auth.py's require_role("admin"))
unmodified. Business logic lives in api/admin_review.py, which itself calls
existing, unmodified decision logic (vacancy_merge.py, CompanySponsorshipSignal)
rather than reimplementing it.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from api import admin_review
from api.auth import require_role
from api.config import ADMIN_EMAIL
from api.database import get_connection
from api.models_api import DedupReviewResolution, SponsorReviewResolution

router = APIRouter(prefix="/admin", tags=["admin-review"], dependencies=[Depends(require_role("admin"))])


@router.get("/dedup-review")
def get_pending_dedup_reviews(conn: Connection = Depends(get_connection)) -> list:
    return admin_review.list_pending_dedup_reviews(conn)


@router.post("/dedup-review/{review_id}/resolve")
def resolve_dedup_review(
    review_id: UUID, payload: DedupReviewResolution, conn: Connection = Depends(get_connection),
) -> dict:
    try:
        return admin_review.resolve_dedup_review(
            conn, review_id, decision=payload.decision, note=payload.note, resolved_by=ADMIN_EMAIL,
        )
    except admin_review.DedupReviewError as exc:
        detail = str(exc)
        status_code = 404 if detail == "not_found" else 409 if detail.startswith("already resolved") else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/sponsor-review")
def get_pending_sponsor_reviews(conn: Connection = Depends(get_connection)) -> list:
    return admin_review.list_pending_sponsor_reviews(conn)


@router.post("/sponsor-review/{vacancy_id}/resolve")
def resolve_sponsor_review(
    vacancy_id: UUID, payload: SponsorReviewResolution, conn: Connection = Depends(get_connection),
) -> dict:
    try:
        return admin_review.resolve_sponsor_review(conn, vacancy_id, decision=payload.decision, note=payload.note)
    except admin_review.SponsorReviewError as exc:
        detail = str(exc)
        status_code = 404 if detail == "not_found" else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/extraction-review")
def get_extraction_review(limit: int = 50, conn: Connection = Depends(get_connection)) -> dict:
    return admin_review.list_extraction_review(conn, limit=limit)
