from datetime import datetime, timedelta, timezone

from canonical_vacancy import canonicalise_raw_vacancy
from job_discovery_access import PreliminaryCampaignPolicy
from job_discovery_pipeline import (
    run_full_job_discovery_cycle,
    run_preliminary_campaign_cycle,
    run_subscription_backfill,
    visible_recommendations_for_talent,
)
from schemas import MatchResult, ResultLane, Talent
from source_schemas import RawVacancyRecord, VacancyLifecycleStatus


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def talent(talent_id="t1", **overrides):
    data = dict(
        talent_id=talent_id,
        full_name=f"Talent {talent_id}",
        email=f"{talent_id}@example.com",
        profile_status="complete",
    )
    data.update(overrides)
    return Talent(**data)


def vacancy(vacancy_id="v1", age_days=1, status=VacancyLifecycleStatus.ACTIVE):
    retrieved_at = NOW - timedelta(days=age_days)
    row = canonicalise_raw_vacancy(
        RawVacancyRecord(
            source_id="greenhouse_public_api",
            source_record_id="board",
            intake_source="public_ats_api",
            acquisition_method="api",
            source_url=f"https://example.com/jobs/{vacancy_id}",
            external_job_id=vacancy_id,
            company_name="Example",
            title=f"Role {vacancy_id}",
            description_text="Description",
            raw_payload={"id": vacancy_id},
            trust_level=4,
            retrieved_at=retrieved_at,
        ),
        vacancy_id=vacancy_id,
    )
    row.lifecycle_status = status
    row.last_seen_at = NOW - timedelta(days=min(age_days, 2))
    return row


def match_for(talent_row, vacancy_row, score=88.0, coverage=82.0, lane=ResultLane.PRIORITY_MATCH):
    return MatchResult(
        talent_id=talent_row.talent_id,
        vacancy_id=vacancy_row.vacancy_id,
        overall_score_percent=score,
        overall_coverage_percent=coverage,
        category_results=[],
        critical_flags=[],
        clarification_flags=[],
        lane=lane,
        provisional=False,
    )


def test_non_subscriber_never_enters_full_matching_or_ai_pipeline():
    calls = {"match": 0, "ai": 0}

    def matcher(talent_row, vacancy_row):
        calls["match"] += 1
        return match_for(talent_row, vacancy_row)

    def explain(talent_row, match, vacancy_row):
        calls["ai"] += 1
        return "AI explanation"

    output = run_full_job_discovery_cycle(
        talents=[talent()],
        vacancies=[vacancy()],
        deterministic_matcher=matcher,
        explanation_generator=explain,
        as_of=NOW,
        access_clock=lambda: NOW,
    )
    assert output.recommendations == []
    assert calls == {"match": 0, "ai": 0}
    assert output.metrics.candidates_skipped == 1


def test_active_subscriber_gets_full_recommendation_and_ai_explanation():
    active = talent(job_discovery_subscription="active")
    output = run_full_job_discovery_cycle(
        talents=[active],
        vacancies=[vacancy()],
        deterministic_matcher=match_for,
        explanation_generator=lambda *args: "Personalised explanation",
        as_of=NOW,
        access_clock=lambda: NOW,
    )
    assert len(output.recommendations) == 1
    assert output.recommendations[0].explanation == "Personalised explanation"
    assert output.metrics.deterministic_matches_run == 1
    assert output.metrics.ai_explanations_generated == 1


def test_access_is_rechecked_before_ai_and_storage():
    active = talent(
        job_discovery_subscription="active",
        subscription_expires_at=NOW + timedelta(minutes=5),
    )
    output = run_full_job_discovery_cycle(
        talents=[active],
        vacancies=[vacancy()],
        deterministic_matcher=match_for,
        explanation_generator=lambda *args: "Should not run",
        as_of=NOW,
        access_clock=lambda: NOW + timedelta(minutes=6),
    )
    assert output.metrics.deterministic_matches_run == 1
    assert output.metrics.ai_explanations_generated == 0
    assert output.recommendations == []


def test_campaign_path_creates_only_lightweight_signals():
    non_subscriber = talent(job_discovery_campaign_opt_in=True)
    output = run_preliminary_campaign_cycle(
        talents=[non_subscriber],
        vacancies=[vacancy()],
        deterministic_matcher=match_for,
        as_of=NOW,
    )
    assert output.recommendations == []
    assert len(output.preliminary_signals) == 1
    signal = output.preliminary_signals[0]
    assert signal.ai_explanation_generated is False
    assert signal.vacancy_details_visible is False
    assert output.metrics.ai_explanations_generated == 0


def test_campaign_path_uses_thresholds_and_signal_cap():
    non_subscriber = talent(job_discovery_campaign_opt_in=True)
    rows = [vacancy(f"v{i}", age_days=i) for i in range(1, 6)]

    def matcher(talent_row, vacancy_row):
        score = {"v1": 95, "v2": 90, "v3": 85, "v4": 65, "v5": 92}[vacancy_row.vacancy_id]
        coverage = 60 if vacancy_row.vacancy_id == "v5" else 85
        return match_for(talent_row, vacancy_row, score=score, coverage=coverage)

    output = run_preliminary_campaign_cycle(
        talents=[non_subscriber],
        vacancies=rows,
        deterministic_matcher=matcher,
        as_of=NOW,
        policy=PreliminaryCampaignPolicy(max_signals_per_talent=2),
    )
    assert [s.vacancy_id for s in output.preliminary_signals] == ["v1", "v2"]


def test_new_subscriber_backfill_uses_recent_14_day_window():
    active = talent(job_discovery_subscription="active")
    recent = vacancy("recent", age_days=4)
    old = vacancy("old", age_days=20)
    output = run_subscription_backfill(
        talent=active,
        vacancies=[old, recent],
        deterministic_matcher=match_for,
        explanation_generator=lambda *args: "Backfill explanation",
        as_of=NOW,
        access_clock=lambda: NOW,
    )
    assert [r.vacancy_id for r in output.recommendations] == ["recent"]
    assert output.metrics.run_type.value == "subscription_backfill"


def test_backfill_orders_fit_before_freshness():
    active = talent(job_discovery_subscription="active")
    newest = vacancy("newest", age_days=0)
    best = vacancy("best", age_days=7)

    def matcher(talent_row, vacancy_row):
        score = 80 if vacancy_row.vacancy_id == "newest" else 95
        return match_for(talent_row, vacancy_row, score=score)

    output = run_subscription_backfill(
        talent=active,
        vacancies=[newest, best],
        deterministic_matcher=matcher,
        explanation_generator=lambda *args: "Explanation",
        as_of=NOW,
        access_clock=lambda: NOW,
    )
    assert [r.vacancy_id for r in output.recommendations] == ["best", "newest"]


def test_existing_recommendations_are_hidden_on_expiry_and_restored_on_renewal():
    active = talent(job_discovery_subscription="active")
    profile = vacancy("v1", age_days=1)
    created = run_full_job_discovery_cycle(
        talents=[active],
        vacancies=[profile],
        deterministic_matcher=match_for,
        explanation_generator=lambda *args: "Explanation",
        as_of=NOW,
        access_clock=lambda: NOW,
    ).recommendations

    expired = active.model_copy(update={"job_discovery_subscription": "expired"})
    assert visible_recommendations_for_talent(
        talent=expired,
        recommendations=created,
        profiles={profile.vacancy_id: profile},
        as_of=NOW,
    ) == []

    renewed = active.model_copy(update={"job_discovery_subscription": "active"})
    visible = visible_recommendations_for_talent(
        talent=renewed,
        recommendations=created,
        profiles={profile.vacancy_id: profile},
        as_of=NOW,
    )
    assert len(visible) == 1


def test_closed_or_unseen_stored_vacancies_do_not_restore():
    active = talent(job_discovery_subscription="active")
    profile = vacancy("v1", age_days=1)
    recommendation = run_full_job_discovery_cycle(
        talents=[active],
        vacancies=[profile],
        deterministic_matcher=match_for,
        explanation_generator=lambda *args: "Explanation",
        as_of=NOW,
        access_clock=lambda: NOW,
    ).recommendations

    profile.lifecycle_status = VacancyLifecycleStatus.CLOSED
    assert visible_recommendations_for_talent(
        talent=active,
        recommendations=recommendation,
        profiles={profile.vacancy_id: profile},
        as_of=NOW,
    ) == []
