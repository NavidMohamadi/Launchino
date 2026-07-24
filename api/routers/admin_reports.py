"""Admin-only reporting/aggregation endpoints (Phase 1 of the admin dashboard).

Read-only: every handler here only calls into api/admin_reports.py's query
functions, which only SELECT and aggregate. Reuses the existing admin auth
(api/auth.py's require_role("admin")) unmodified.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from api import admin_reports
from api.auth import require_role
from api.database import get_connection

router = APIRouter(prefix="/admin", tags=["admin-reports"], dependencies=[Depends(require_role("admin"))])


@router.get("/reports/signups")
def get_signups_over_time(
    granularity: str = Query(default="day", description="day | week | month"),
    conn: Connection = Depends(get_connection),
) -> dict:
    try:
        return admin_reports.signups_over_time(conn, granularity=granularity)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reports/candidate-activity")
def get_candidate_activity(
    window_days: int = Query(default=admin_reports.ACTIVE_WINDOW_DAYS, ge=1),
    conn: Connection = Depends(get_connection),
) -> dict:
    return admin_reports.candidate_activity(conn, window_days=window_days)


@router.get("/reports/subscriptions")
def get_subscription_breakdown(conn: Connection = Depends(get_connection)) -> dict:
    return admin_reports.subscription_breakdown(conn)


@router.get("/candidates/{talent_id}/report")
def get_candidate_report(talent_id: UUID, conn: Connection = Depends(get_connection)) -> dict:
    report = admin_reports.candidate_report(conn, talent_id)
    if not report:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return report


@router.get("/companies/{company_id}/report")
def get_company_report(company_id: UUID, conn: Connection = Depends(get_connection)) -> dict:
    report = admin_reports.company_report(conn, company_id)
    if not report:
        raise HTTPException(status_code=404, detail="Company not found")
    return report


@router.get("/reports/ingestion-health")
def get_ingestion_health(conn: Connection = Depends(get_connection)) -> list:
    return admin_reports.ingestion_health(conn)
