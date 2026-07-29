"""Read-only aggregation queries for the admin dashboard (Phase 1).

Every function here only SELECTs and aggregates -- none of them write to
ai_usage_log, job_recommendation, vacancy, talent, or any other table. Pure
query/aggregation logic lives here; api/routers/admin_reports.py wires it to
HTTP + the existing admin auth (api/auth.py's require_role("admin")), reusing
that unmodified.

Two real, previously-missing data points this phase depends on (see
PROJECT_NOTES.md for the fuller writeup of why they were added):
  - talent.last_login_at / company.last_login_at -- set only by a successful
    POST /candidates/login or /companies/login (and at registration, since a
    just-registered account is trivially "active", not dormant until its next
    login).
  - talent_element_value.created_at -- insertion time of each answer version;
    last_confirmed_at already existed but is an optional, caller-supplied
    "candidate reconfirmed this" date, not reliably populated on every submit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.candidate_service import resolve_candidate_element_activation

# Default "recent" window for the active/dormant candidate split. Named
# constant, not hardcoded inline, per the task -- callers may override via
# the endpoint's query param.
ACTIVE_WINDOW_DAYS = 30

VALID_GRANULARITIES = {"day", "week", "month"}

# result_lane values that count as "shortlisted" for the per-company report.
# Not a literal column -- src/database_schema.sql's match_summary.result_lane
# check constraint lists ('priority_match','promising_match','clarification_required',
# 'critical_review','lower_alignment'); the two "match" lanes are the ones a
# company would reasonably act on, so that's the definition used here.
SHORTLISTED_LANES = ("priority_match", "promising_match")


def signups_over_time(conn: Connection, *, granularity: str = "day") -> Dict[str, List[Dict[str, Any]]]:
    if granularity not in VALID_GRANULARITIES:
        raise ValueError(f"granularity must be one of {sorted(VALID_GRANULARITIES)}, got {granularity!r}")

    candidate_rows = conn.execute(
        text("select date_trunc(:granularity, created_at) as period, count(*) as count from talent group by period order by period"),
        {"granularity": granularity},
    ).all()
    company_rows = conn.execute(
        text("select date_trunc(:granularity, created_at) as period, count(*) as count from company group by period order by period"),
        {"granularity": granularity},
    ).all()
    return {
        "granularity": granularity,
        "candidates": [{"period": r.period.isoformat(), "count": r.count} for r in candidate_rows],
        "companies": [{"period": r.period.isoformat(), "count": r.count} for r in company_rows],
    }


def candidate_activity(conn: Connection, *, window_days: int = ACTIVE_WINDOW_DAYS) -> Dict[str, Any]:
    """Active = last_login_at within the window, OR any talent_element_value
    row (any element, any version) created within the window. Everyone else
    is dormant -- including a candidate who registered but never logged in
    again and has never answered anything, which is a real, meaningful
    "dormant" case, not a data gap."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    row = conn.execute(
        text(
            """
            select
                count(*) filter (where is_active) as active_count,
                count(*) filter (where not is_active) as dormant_count
            from (
                select t.talent_id,
                    (
                        -- coalesce is required: last_login_at is NULL for every
                        -- pre-existing candidate from before this column existed,
                        -- and "NULL >= cutoff" is NULL (not false) in SQL's
                        -- three-valued logic -- "NULL or false" is still NULL,
                        -- which "filter (where not is_active)" then silently
                        -- excludes from BOTH buckets instead of counting as
                        -- dormant. Found via real data: an 11-candidate table
                        -- reported 2 active + 0 dormant before this fix.
                        coalesce(t.last_login_at >= :cutoff, false)
                        or exists (
                            select 1 from talent_element_value v
                            where v.talent_id = t.talent_id and v.created_at >= :cutoff
                        )
                    ) as is_active
                from talent t
            ) sub
            """
        ),
        {"cutoff": cutoff},
    ).first()
    return {
        "window_days": window_days,
        "active_count": row.active_count,
        "dormant_count": row.dormant_count,
    }


def subscription_breakdown(conn: Connection) -> Dict[str, Any]:
    """Non-subscriber, for the opt-in rate, means job_discovery_subscription='none'
    specifically (not 'expired') -- a lapsed subscriber already made a
    different kind of decision than someone who never subscribed at all."""
    by_status = conn.execute(
        text("select job_discovery_subscription, count(*) as count from talent group by job_discovery_subscription")
    ).all()
    opt_in_row = conn.execute(
        text(
            """
            select
                count(*) filter (where job_discovery_campaign_opt_in) as opted_in,
                count(*) as total
            from talent where job_discovery_subscription = 'none'
            """
        )
    ).first()
    opt_in_rate = (opt_in_row.opted_in / opt_in_row.total) if opt_in_row.total else None
    return {
        "by_status": {r.job_discovery_subscription: r.count for r in by_status},
        "non_subscriber_campaign_opt_in": {
            "opted_in": opt_in_row.opted_in, "total_non_subscribers": opt_in_row.total, "rate": opt_in_rate,
        },
    }


def _candidate_coverage(conn: Connection, talent_id: UUID) -> Dict[str, Any]:
    # The per-element "what's active and answered" rule now lives only in
    # api/candidate_service.py's resolve_candidate_element_activation (also
    # used by the candidate dashboard's per-category completion endpoint) --
    # this just collapses that same result to one overall figure.
    activation = resolve_candidate_element_activation(conn, talent_id)
    total_active = sum(1 for v in activation.values() if v["active"])
    answered_active = sum(1 for v in activation.values() if v["active"] and v["answered"])

    coverage_percent = (answered_active / total_active * 100) if total_active else 0.0
    return {
        "elements_active_for_candidate": total_active,
        "elements_answered": answered_active,
        "coverage_percent": round(coverage_percent, 1),
    }


def candidate_report(conn: Connection, talent_id: UUID) -> Optional[Dict[str, Any]]:
    talent_row = conn.execute(
        text("select talent_id, full_name, email from talent where talent_id = :talent_id"),
        {"talent_id": str(talent_id)},
    ).mappings().first()
    if not talent_row:
        return None

    coverage = _candidate_coverage(conn, talent_id)

    recommendations = conn.execute(
        text(
            """
            select recommendation_id, vacancy_id, result_lane, overall_score, overall_coverage,
                   provisional_public_match, generated_at
            from job_recommendation where talent_id = :talent_id order by generated_at desc
            """
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()

    total_cost = conn.execute(
        text("select coalesce(sum(estimated_cost_usd), 0) as total from ai_usage_log where talent_id = :talent_id"),
        {"talent_id": str(talent_id)},
    ).scalar_one()

    return {
        "talent_id": str(talent_row["talent_id"]),
        "full_name": talent_row["full_name"],
        "email": talent_row["email"],
        "profile_completeness": coverage,
        "recommendations": [
            {
                "recommendation_id": str(r["recommendation_id"]), "vacancy_id": str(r["vacancy_id"]),
                "result_lane": r["result_lane"], "overall_score": float(r["overall_score"]) if r["overall_score"] is not None else None,
                "overall_coverage": float(r["overall_coverage"]), "provisional_public_match": r["provisional_public_match"],
                "generated_at": r["generated_at"].isoformat(),
            }
            for r in recommendations
        ],
        "total_ai_cost_usd": float(total_cost),
    }


def company_report(conn: Connection, company_id: UUID) -> Optional[Dict[str, Any]]:
    company_row = conn.execute(
        text("select company_id, legal_name, display_name from company where company_id = :company_id"),
        {"company_id": str(company_id)},
    ).mappings().first()
    if not company_row:
        return None

    vacancies = conn.execute(
        text("select vacancy_id, role_title, lifecycle_status from vacancy where company_id = :company_id order by created_at desc"),
        {"company_id": str(company_id)},
    ).mappings().all()

    match_run_count = conn.execute(
        text(
            "select count(*) from match_run mr join vacancy v on v.vacancy_id = mr.vacancy_id "
            "where v.company_id = :company_id"
        ),
        {"company_id": str(company_id)},
    ).scalar_one()

    shortlisted_by_vacancy = conn.execute(
        text(
            """
            select v.vacancy_id, v.role_title, count(distinct ms.talent_id) as shortlisted_count
            from vacancy v
            join match_run mr on mr.vacancy_id = v.vacancy_id
            join match_summary ms on ms.match_run_id = mr.match_run_id and ms.result_lane = any(:lanes)
            where v.company_id = :company_id
            group by v.vacancy_id, v.role_title
            """
        ),
        {"company_id": str(company_id), "lanes": list(SHORTLISTED_LANES)},
    ).mappings().all()

    total_cost = conn.execute(
        text(
            "select coalesce(sum(estimated_cost_usd), 0) as total from ai_usage_log "
            "where vacancy_id in (select vacancy_id from vacancy where company_id = :company_id)"
        ),
        {"company_id": str(company_id)},
    ).scalar_one()

    return {
        "company_id": str(company_row["company_id"]),
        "legal_name": company_row["legal_name"],
        "display_name": company_row["display_name"],
        "vacancies_posted": len(vacancies),
        "vacancies": [
            {"vacancy_id": str(v["vacancy_id"]), "title": v["role_title"], "lifecycle_status": v["lifecycle_status"]}
            for v in vacancies
        ],
        "match_runs": match_run_count,
        "shortlisted_lanes": list(SHORTLISTED_LANES),
        "shortlisted_by_vacancy": [
            {"vacancy_id": str(r["vacancy_id"]), "title": r["role_title"], "shortlisted_count": r["shortlisted_count"]}
            for r in shortlisted_by_vacancy
        ],
        "total_ai_cost_usd": float(total_cost),
    }


def ingestion_health(conn: Connection) -> List[Dict[str, Any]]:
    """last_polled_at means "attempted", not "succeeded" -- mark_polled() in
    api/job_discovery_scheduler.py stamps it for every due source regardless
    of validation outcome, by design (so a dead board isn't retried every
    cycle). The per-source success/failure signal is poll_run, populated by
    that same module since this phase -- a source with last_polled_at set but
    zero poll_run rows was polled before that write path existed, so its real
    last status is genuinely unknown, not "ok" or "failing"; reported as such
    rather than guessed."""
    rows = conn.execute(
        text(
            """
            select cjs.source_record_id, cjs.company_id, c.display_name as company_name, cjs.source_id,
                   cjs.board_identifier, cjs.enabled, cjs.last_polled_at, cjs.next_poll_at,
                   pr.status as last_status, pr.jobs_seen as last_jobs_seen,
                   pr.jobs_created as last_jobs_created, pr.jobs_updated as last_jobs_updated,
                   pr.error_message as last_error, pr.completed_at as last_poll_completed_at
            from company_job_source cjs
            join company c on c.company_id = cjs.company_id
            left join lateral (
                select * from poll_run where source_record_id = cjs.source_record_id
                order by completed_at desc limit 1
            ) pr on true
            order by c.display_name, cjs.source_id
            """
        )
    ).mappings().all()

    results = []
    for r in rows:
        if r["last_status"] is not None:
            health = "ok" if r["last_status"] == "ok" else r["last_status"]  # "empty" | "error" pass through as-is
        elif r["last_polled_at"] is not None:
            health = "unknown (polled before poll_run logging existed)"
        else:
            health = "never polled"
        results.append({
            "source_record_id": str(r["source_record_id"]),
            "company_id": str(r["company_id"]),
            "company_name": r["company_name"],
            "source_id": r["source_id"],
            "board_identifier": r["board_identifier"],
            "enabled": r["enabled"],
            "last_polled_at": r["last_polled_at"].isoformat() if r["last_polled_at"] else None,
            "next_poll_at": r["next_poll_at"].isoformat() if r["next_poll_at"] else None,
            "last_poll_health": health,
            "last_jobs_seen": r["last_jobs_seen"],
            "last_jobs_created": r["last_jobs_created"],
            "last_jobs_updated": r["last_jobs_updated"],
            "last_error": r["last_error"],
        })
    return results
