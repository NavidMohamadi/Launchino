from canonical_vacancy import canonicalise_raw_vacancy
from job_recommendations import rank_jobs_for_talent
from schemas import MatchResult, ResultLane
from source_schemas import RawVacancyRecord


def vacancy():
    return canonicalise_raw_vacancy(RawVacancyRecord(
        source_id="greenhouse_public_api", source_record_id="b", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com/jobs/1", external_job_id="1",
        company_name="Example", title="Role", description_text="Description", raw_payload={"id": 1}, trust_level=4,
    ))


def match(vacancy_id):
    return MatchResult(
        talent_id="t1", vacancy_id=vacancy_id, overall_score_percent=88,
        overall_coverage_percent=80, category_results=[], critical_flags=[], clarification_flags=[],
        lane=ResultLane.PRIORITY_MATCH, provisional=False,
    )


def test_public_job_recommendation_is_provisional():
    profile = vacancy()
    rows = rank_jobs_for_talent("t1", [match(profile.vacancy_id)], {profile.vacancy_id: profile})
    assert rows[0].provisional_public_match is True
    assert "Preliminary alignment" in rows[0].explanation


def test_closed_stale_and_archived_vacancies_are_not_recommended():
    from source_schemas import VacancyLifecycleStatus

    profiles = []
    matches = []
    for status in (
        VacancyLifecycleStatus.STALE,
        VacancyLifecycleStatus.CLOSED,
        VacancyLifecycleStatus.ARCHIVED,
    ):
        profile = vacancy()
        profile.vacancy_id = f"vac-{status.value}"
        profile.lifecycle_status = status
        profiles.append(profile)
        matches.append(match(profile.vacancy_id))

    rows = rank_jobs_for_talent("t1", matches, {p.vacancy_id: p for p in profiles})
    assert rows == []


def test_updated_vacancy_remains_recommendable():
    from source_schemas import VacancyLifecycleStatus

    profile = vacancy()
    profile.lifecycle_status = VacancyLifecycleStatus.UPDATED
    rows = rank_jobs_for_talent("t1", [match(profile.vacancy_id)], {profile.vacancy_id: profile})
    assert len(rows) == 1
