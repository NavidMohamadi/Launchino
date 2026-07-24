"""Persistence for src/job_discovery_pipeline.py's output: job_discovery_batch_run
and job_recommendation. Straight round-trip of JobDiscoveryBatchMetrics /
JobRecommendation (both in src/source_schemas.py); no scoring or entitlement
logic lives here.

match_run_id is left NULL on every row inserted here: run_full_job_discovery_cycle's
deterministic_matcher (api/job_discovery_runner.py) computes MatchResult objects
directly rather than persisting a match_run per (talent, vacancy) pairing it
merely considers (most pairings never become a recommendation) -- only the
existing POST /vacancies/{id}/match endpoint persists match_run rows today.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from source_schemas import JobDiscoveryBatchMetrics, JobRecommendation


def insert_batch_run(conn: Connection, metrics: JobDiscoveryBatchMetrics) -> UUID:
    batch_run_id = uuid4()
    conn.execute(
        text(
            """
            insert into job_discovery_batch_run (
                batch_run_id, run_type, started_at, completed_at, candidates_considered,
                candidates_included, candidates_skipped, vacancies_considered,
                deterministic_matches_run, ai_explanations_generated, recommendations_created,
                preliminary_signals_created, configuration
            ) values (
                :batch_run_id, :run_type, :started_at, :completed_at, :candidates_considered,
                :candidates_included, :candidates_skipped, :vacancies_considered,
                :deterministic_matches_run, :ai_explanations_generated, :recommendations_created,
                :preliminary_signals_created, cast('{}' as jsonb)
            )
            """
        ),
        {
            "batch_run_id": str(batch_run_id),
            "run_type": metrics.run_type.value,
            "started_at": metrics.started_at,
            "completed_at": None,
            "candidates_considered": metrics.candidates_considered,
            "candidates_included": metrics.candidates_included,
            "candidates_skipped": metrics.candidates_skipped,
            "vacancies_considered": metrics.vacancies_considered,
            "deterministic_matches_run": metrics.deterministic_matches_run,
            "ai_explanations_generated": metrics.ai_explanations_generated,
            "recommendations_created": metrics.recommendations_created,
            "preliminary_signals_created": metrics.preliminary_signals_created,
        },
    )
    return batch_run_id


def insert_recommendation(conn: Connection, *, batch_run_id: UUID, recommendation: JobRecommendation) -> None:
    """SQL's unique (talent_id, vacancy_id, match_run_id) constraint does not
    fire when match_run_id is NULL -- NULLs are never equal to each other for
    uniqueness purposes, so ON CONFLICT on that tuple silently never matches
    here. Re-running a batch would create duplicate recommendation rows
    instead of updating the existing one (the same class of bug already
    fixed once for vacancy_dedup_review -- see PROJECT_NOTES.md), so this
    does an explicit check instead of relying on ON CONFLICT."""
    match = recommendation.match_result
    params = {
        "batch_run_id": str(batch_run_id),
        "talent_id": recommendation.talent_id,
        "vacancy_id": recommendation.vacancy_id,
        "result_lane": match.lane.value,
        "overall_score": match.overall_score_percent,
        "overall_coverage": match.overall_coverage_percent,
        "vacancy_verification_status": recommendation.vacancy_verification_status.value,
        "weighting_mode": recommendation.weighting_mode.value,
        "provisional_public_match": recommendation.provisional_public_match,
        "source_url": recommendation.source_url,
        "explanation": recommendation.explanation,
    }
    existing = conn.execute(
        text(
            "select recommendation_id from job_recommendation "
            "where talent_id = :talent_id and vacancy_id = :vacancy_id and match_run_id is null"
        ),
        params,
    ).first()
    if existing:
        conn.execute(
            text(
                """
                update job_recommendation set
                    batch_run_id = :batch_run_id, result_lane = :result_lane, overall_score = :overall_score,
                    overall_coverage = :overall_coverage, vacancy_verification_status = :vacancy_verification_status,
                    weighting_mode = :weighting_mode, provisional_public_match = :provisional_public_match,
                    source_url = :source_url, explanation = :explanation, generated_at = now()
                where recommendation_id = :recommendation_id
                """
            ),
            {**params, "recommendation_id": existing[0]},
        )
    else:
        conn.execute(
            text(
                """
                insert into job_recommendation (
                    recommendation_id, batch_run_id, talent_id, vacancy_id, match_run_id, result_lane,
                    overall_score, overall_coverage, vacancy_verification_status, weighting_mode,
                    provisional_public_match, source_url, explanation
                ) values (
                    gen_random_uuid(), :batch_run_id, :talent_id, :vacancy_id, null, :result_lane,
                    :overall_score, :overall_coverage, :vacancy_verification_status, :weighting_mode,
                    :provisional_public_match, :source_url, :explanation
                )
                """
            ),
            params,
        )
