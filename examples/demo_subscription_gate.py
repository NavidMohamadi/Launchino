from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from canonical_vacancy import canonicalise_raw_vacancy
from job_discovery_access import campaign_teaser_text
from job_discovery_pipeline import (
    run_full_job_discovery_cycle,
    run_preliminary_campaign_cycle,
    run_subscription_backfill,
    visible_recommendations_for_talent,
)
from schemas import JobDiscoverySubscription, MatchResult, ResultLane, Talent
from source_schemas import RawVacancyRecord


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
OUT = Path(__file__).with_name("demo_subscription_gate_output.json")


def make_talent(talent_id: str, status: JobDiscoverySubscription, campaign_opt_in: bool) -> Talent:
    return Talent(
        talent_id=talent_id,
        full_name=f"Demo {talent_id}",
        email=f"{talent_id}@example.com",
        profile_status="complete",
        job_discovery_subscription=status,
        subscription_expires_at=None,
        job_discovery_campaign_opt_in=campaign_opt_in,
    )


def make_vacancy(vacancy_id: str, age_days: int):
    return canonicalise_raw_vacancy(
        RawVacancyRecord(
            source_id="greenhouse_public_api",
            source_record_id="demo-board",
            intake_source="public_ats_api",
            acquisition_method="api",
            source_url=f"https://example.com/jobs/{vacancy_id}",
            external_job_id=vacancy_id,
            company_name="Demo Company",
            title=f"Demo Role {vacancy_id}",
            description_text="A public demo vacancy.",
            raw_payload={"id": vacancy_id},
            trust_level=4,
            retrieved_at=NOW - timedelta(days=age_days),
        ),
        vacancy_id=vacancy_id,
    )


def matcher(talent: Talent, vacancy) -> MatchResult:
    score = 91 if vacancy.vacancy_id == "vacancy-new" else 84
    return MatchResult(
        talent_id=talent.talent_id,
        vacancy_id=vacancy.vacancy_id,
        overall_score_percent=score,
        overall_coverage_percent=86,
        category_results=[],
        critical_flags=[],
        clarification_flags=[],
        lane=ResultLane.PRIORITY_MATCH,
        provisional=False,
    )


def explain(talent: Talent, match: MatchResult, vacancy) -> str:
    return (
        f"Personalised explanation for {talent.talent_id}: {vacancy.title} "
        f"has {match.overall_score_percent:.0f}% preliminary alignment."
    )


def main() -> None:
    subscriber = make_talent("subscriber", JobDiscoverySubscription.ACTIVE, False)
    non_subscriber = make_talent("non-subscriber", JobDiscoverySubscription.NONE, True)
    recent = make_vacancy("vacancy-new", 2)
    older = make_vacancy("vacancy-old", 18)

    full = run_full_job_discovery_cycle(
        talents=[subscriber, non_subscriber],
        vacancies=[recent],
        deterministic_matcher=matcher,
        explanation_generator=explain,
        as_of=NOW,
        access_clock=lambda: NOW,
    )

    campaign = run_preliminary_campaign_cycle(
        talents=[subscriber, non_subscriber],
        vacancies=[recent, older],
        deterministic_matcher=matcher,
        as_of=NOW,
    )

    backfill = run_subscription_backfill(
        talent=subscriber,
        vacancies=[recent, older],
        deterministic_matcher=matcher,
        explanation_generator=explain,
        as_of=NOW,
        access_clock=lambda: NOW,
    )

    expired = subscriber.model_copy(
        update={"job_discovery_subscription": JobDiscoverySubscription.EXPIRED}
    )
    hidden = visible_recommendations_for_talent(
        talent=expired,
        recommendations=full.recommendations,
        profiles={recent.vacancy_id: recent},
        as_of=NOW,
    )
    restored = visible_recommendations_for_talent(
        talent=subscriber,
        recommendations=full.recommendations,
        profiles={recent.vacancy_id: recent},
        as_of=NOW,
    )

    payload = {
        "full_pipeline": {
            "recommendation_talents": [row.talent_id for row in full.recommendations],
            "metrics": full.metrics.model_dump(mode="json"),
        },
        "campaign_pipeline": {
            "signal_talents": [row.talent_id for row in campaign.preliminary_signals],
            "teaser": campaign_teaser_text(len(campaign.preliminary_signals)),
            "metrics": campaign.metrics.model_dump(mode="json"),
        },
        "subscription_backfill": {
            "vacancies": [row.vacancy_id for row in backfill.recommendations],
            "metrics": backfill.metrics.model_dump(mode="json"),
        },
        "access_after_expiry": {
            "visible_count_while_expired": len(hidden),
            "visible_count_after_renewal": len(restored),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
