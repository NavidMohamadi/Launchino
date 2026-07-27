"""Manually-triggered real run of src/job_discovery_pipeline.py's full cycle.

Like api/job_discovery_scheduler.py, this is never imported by api/main.py and
registers no scheduler, cron, or background task. The only way to run it is:

    python -m api.job_discovery_runner --run-once

Loads real talents/vacancies from Postgres, builds a deterministic_matcher
from the unmodified src/matching_service-equivalent logic (build_item_results +
aggregate_match) and an explanation_generator that calls the real Claude API
(api/explanation_service.py), then hands both to
src/job_discovery_pipeline.py's run_full_job_discovery_cycle exactly as its
own docstring describes -- entitlement gating, deterministic matching and
lane assignment are all unmodified; this module only supplies the two
callables the pipeline asks for and persists what it returns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from job_discovery_pipeline import run_full_job_discovery_cycle
from match_engine import aggregate_match
from schemas import FitElement, MatchConfiguration, MatchResult, Talent
from source_schemas import CanonicalVacancyProfile

from api.explanation_service import generate_match_explanation
from api.job_discovery_store import insert_batch_run, insert_recommendation
from api.matching_service import _flag_categories_with_no_data, build_item_results, load_dictionary, load_talent_values
from api.vacancy_store import load_element_values, row_to_profile


def load_all_talents(conn: Connection) -> List[Talent]:
    rows = conn.execute(text("select * from talent")).mappings().all()
    return [
        Talent(
            talent_id=str(row["talent_id"]), full_name=row["full_name"], email=row["email"],
            profile_status=row["profile_status"], job_discovery_subscription=row["job_discovery_subscription"],
            subscription_expires_at=row["subscription_expires_at"],
            job_discovery_campaign_opt_in=row["job_discovery_campaign_opt_in"],
            subscription_updated_at=row["subscription_updated_at"], subscription_source=row["subscription_source"],
        )
        for row in rows
    ]


def load_recommendable_vacancies(conn: Connection) -> List[CanonicalVacancyProfile]:
    rows = conn.execute(
        text("select * from vacancy where lifecycle_status in ('active', 'updated')")
    ).mappings().all()
    return [row_to_profile(row, element_values=load_element_values(conn, row["vacancy_id"])) for row in rows]


def _vacancy_values_dict(profile: CanonicalVacancyProfile) -> Dict[str, Dict[str, Any]]:
    return {
        ev.element_id: {
            "value": ev.value, "value_status": ev.value_status.value,
            "item_importance": ev.item_importance, "requirement_type": ev.requirement_type.value,
        }
        for ev in profile.element_values
    }


def make_deterministic_matcher(
    conn: Connection, dictionary: Dict[str, FitElement],
) -> Callable[[Talent, CanonicalVacancyProfile], MatchResult]:
    talent_values_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def matcher(talent: Talent, vacancy: CanonicalVacancyProfile) -> MatchResult:
        if talent.talent_id not in talent_values_cache:
            talent_values_cache[talent.talent_id] = load_talent_values(conn, talent.talent_id)
        item_results = build_item_results(
            talent_id=talent.talent_id, vacancy_id=vacancy.vacancy_id, dictionary=dictionary,
            talent_values=talent_values_cache[talent.talent_id], vacancy_values=_vacancy_values_dict(vacancy),
        )
        config = MatchConfiguration(vacancy_id=vacancy.vacancy_id, category_weights=vacancy.category_weights)
        result = aggregate_match(
            talent_id=talent.talent_id, vacancy_id=vacancy.vacancy_id, item_results=item_results, config=config,
        )
        return _flag_categories_with_no_data(result, config=config)

    return matcher


def make_explanation_generator() -> Callable[[Talent, MatchResult, CanonicalVacancyProfile], str]:
    def generator(talent: Talent, match: MatchResult, vacancy: CanonicalVacancyProfile) -> str:
        return generate_match_explanation(talent=talent, match_result=match, vacancy=vacancy)

    return generator


def run_real_job_discovery_cycle(conn: Connection, *, as_of: Optional[datetime] = None) -> dict:
    as_of = as_of or datetime.now(timezone.utc)
    dictionary = load_dictionary(conn)
    talents = load_all_talents(conn)
    vacancies = load_recommendable_vacancies(conn)

    output = run_full_job_discovery_cycle(
        talents=talents, vacancies=vacancies,
        deterministic_matcher=make_deterministic_matcher(conn, dictionary),
        explanation_generator=make_explanation_generator(), as_of=as_of,
    )

    batch_run_id = insert_batch_run(conn, output.metrics)
    for recommendation in output.recommendations:
        insert_recommendation(conn, batch_run_id=batch_run_id, recommendation=recommendation)

    return {"batch_run_id": batch_run_id, "output": output}


def _print_report(result: dict) -> None:
    metrics = result["output"].metrics
    print(f"batch_run_id: {result['batch_run_id']}")
    print(f"candidates considered: {metrics.candidates_considered}")
    print(f"candidates included (active subscription): {metrics.candidates_included}")
    print(f"candidates skipped: {metrics.candidates_skipped}")
    print(f"vacancies considered: {metrics.vacancies_considered}")
    print(f"deterministic matches run: {metrics.deterministic_matches_run}")
    print(f"AI explanations generated: {metrics.ai_explanations_generated}")
    print(f"recommendations created: {metrics.recommendations_created}")
    for rec in result["output"].recommendations:
        print(f"  - talent={rec.talent_id} vacancy={rec.vacancy_id} lane={rec.match_result.lane.value} "
              f"score={rec.match_result.overall_score_percent}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", help="Run one real job discovery cycle.")
    args = parser.parse_args()

    if args.run_once:
        from api.database import engine
        with engine.begin() as conn:
            _print_report(run_real_job_discovery_cycle(conn))
    else:
        parser.print_help()
