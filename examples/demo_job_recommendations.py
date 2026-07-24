from __future__ import annotations

import json

from canonical_vacancy import canonicalise_raw_vacancy
from job_recommendations import rank_jobs_for_talent
from schemas import MatchResult, ResultLane
from source_schemas import RawVacancyRecord


def main():
    profile = canonicalise_raw_vacancy(RawVacancyRecord(
        source_id="greenhouse_public_api",
        source_record_id="exampleanalytics",
        intake_source="public_ats_api",
        acquisition_method="api",
        source_url="https://boards.greenhouse.io/exampleanalytics/jobs/101",
        external_job_id="101",
        company_name="Example Analytics",
        company_domain="example-analytics.nl",
        title="Junior Supply Chain Analyst",
        description_text="Analyse operational data and improve planning processes.",
        location_text="Eindhoven",
        raw_payload={"id": 101},
        trust_level=4,
    ))
    match = MatchResult(
        talent_id="talent-demo",
        vacancy_id=profile.vacancy_id,
        overall_score_percent=84.0,
        overall_coverage_percent=72.0,
        category_results=[],
        critical_flags=[],
        clarification_flags=["PRACT-SPONSOR"],
        lane=ResultLane.CLARIFICATION_REQUIRED,
        provisional=True,
    )
    rows = rank_jobs_for_talent("talent-demo", [match], {profile.vacancy_id: profile})
    print(json.dumps([r.model_dump(mode="json") for r in rows], indent=2))


if __name__ == "__main__":
    main()
