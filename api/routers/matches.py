from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import check_vacancy_ownership, require_role
from api.database import get_connection
from api.matching_service import get_talent, get_vacancy, run_match
from api.models_api import CategoryResultOut, MatchResultOut, MatchRunOut, MatchRunRequest
from schemas import MatchConfiguration

router = APIRouter(prefix="/vacancies", tags=["matches"])
match_run_router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("/{vacancy_id}/match", response_model=MatchRunOut, status_code=201)
def run_match_endpoint(
    vacancy_id: UUID, payload: MatchRunRequest, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("company", "admin")),
) -> MatchRunOut:
    vacancy_row = get_vacancy(conn, vacancy_id)
    if not vacancy_row:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    check_vacancy_ownership(claims, vacancy_row["company_id"])
    for talent_id in payload.talent_ids:
        if not get_talent(conn, talent_id):
            raise HTTPException(status_code=404, detail=f"Candidate not found: {talent_id}")

    try:
        config = MatchConfiguration(
            vacancy_id=str(vacancy_id),
            algorithm_version=payload.algorithm_version,
            category_weights=payload.category_weights,
            minimum_overall_coverage=payload.minimum_overall_coverage,
            minimum_category_coverage=payload.minimum_category_coverage,
            priority_score_threshold=payload.priority_score_threshold,
            promising_score_threshold=payload.promising_score_threshold,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    outcome = run_match(
        conn, vacancy_id=vacancy_id, talent_ids=payload.talent_ids, config=config,
        approved_by=payload.approved_by, weighting_mode=vacancy_row["weighting_mode"],
    )

    results = [
        MatchResultOut(
            talent_id=result.talent_id, vacancy_id=result.vacancy_id,
            overall_score_percent=result.overall_score_percent,
            overall_coverage_percent=result.overall_coverage_percent,
            category_results=[CategoryResultOut(**cr.model_dump()) for cr in result.category_results],
            critical_flags=result.critical_flags, clarification_flags=result.clarification_flags,
            lane=result.lane.value, provisional=result.provisional,
        )
        for result in outcome["results"]
    ]
    return MatchRunOut(
        match_run_id=outcome["match_run_id"], vacancy_id=vacancy_id,
        algorithm_version=payload.algorithm_version, results=results,
    )


@match_run_router.get("/{match_run_id}")
def get_match_run(
    match_run_id: UUID, conn: Connection = Depends(get_connection),
    claims: dict = Depends(require_role("candidate", "company", "admin")),
) -> dict:
    run_row = conn.execute(
        text("select * from match_run where match_run_id = :id"), {"id": str(match_run_id)}
    ).mappings().first()
    if not run_row:
        raise HTTPException(status_code=404, detail="Match run not found")
    summaries = conn.execute(
        text("select * from match_summary where match_run_id = :id"), {"id": str(match_run_id)}
    ).mappings().all()

    # Role-scoped view, not a single ownership check: a company sees the full run for
    # its own vacancy; a candidate sees only their own row within it (never another
    # candidate's), regardless of vacancy ownership; admin sees everything.
    if claims["role"] == "company":
        vacancy_row = conn.execute(
            text("select company_id from vacancy where vacancy_id = :id"), {"id": str(run_row["vacancy_id"])}
        ).mappings().first()
        check_vacancy_ownership(claims, vacancy_row["company_id"] if vacancy_row else None)
    elif claims["role"] == "candidate":
        summaries = [s for s in summaries if str(s["talent_id"]) == claims["sub"]]
        if not summaries:
            raise HTTPException(status_code=403, detail="Cannot access this match run")

    return {"match_run": dict(run_row), "summaries": [dict(s) for s in summaries]}
