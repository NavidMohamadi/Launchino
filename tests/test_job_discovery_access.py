from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from canonical_vacancy import canonicalise_raw_vacancy
from job_discovery_access import (
    JobDiscoveryEntitlementService,
    PreliminaryCampaignEligibilityService,
    campaign_teaser_text,
    is_fresh_for_restored_access,
    select_recent_recommendable_vacancies,
)
from schemas import JobDiscoverySubscription, Talent
from source_schemas import RawVacancyRecord, VacancyLifecycleStatus


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def talent(**overrides):
    data = dict(
        talent_id="talent-1",
        full_name="Talent One",
        email="talent@example.com",
        profile_status="complete",
    )
    data.update(overrides)
    return Talent(**data)


def vacancy(vacancy_id: str, first_seen_at: datetime):
    raw = RawVacancyRecord(
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
        retrieved_at=first_seen_at,
    )
    return canonicalise_raw_vacancy(raw, vacancy_id=vacancy_id)


def test_active_null_expiry_is_allowed_for_mvp():
    service = JobDiscoveryEntitlementService()
    row = talent(job_discovery_subscription="active", subscription_expires_at=None)
    assert service.has_active_access(row, as_of=NOW) is True


def test_none_expired_and_past_expiry_are_blocked():
    service = JobDiscoveryEntitlementService()
    assert service.has_active_access(talent(), as_of=NOW) is False
    assert service.has_active_access(
        talent(job_discovery_subscription="expired"), as_of=NOW
    ) is False
    assert service.has_active_access(
        talent(
            job_discovery_subscription="active",
            subscription_expires_at=NOW - timedelta(seconds=1),
        ),
        as_of=NOW,
    ) is False


def test_active_future_expiry_is_allowed():
    row = talent(
        job_discovery_subscription=JobDiscoverySubscription.ACTIVE,
        subscription_expires_at=NOW + timedelta(days=30),
    )
    assert JobDiscoveryEntitlementService().has_active_access(row, as_of=NOW)


def test_subscription_timestamps_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        talent(
            job_discovery_subscription="active",
            subscription_expires_at=datetime(2026, 8, 1, 0, 0),
        )


def test_campaign_eligibility_is_separate_from_subscription_access():
    service = PreliminaryCampaignEligibilityService()
    non_subscriber = talent(job_discovery_campaign_opt_in=True)
    active = talent(
        talent_id="active",
        email="active@example.com",
        job_discovery_subscription="active",
        job_discovery_campaign_opt_in=True,
    )
    incomplete = talent(
        talent_id="incomplete",
        email="incomplete@example.com",
        profile_status="registered",
        job_discovery_campaign_opt_in=True,
    )
    assert service.is_eligible(non_subscriber, as_of=NOW)
    assert not service.is_eligible(active, as_of=NOW)
    assert not service.is_eligible(incomplete, as_of=NOW)


def test_recent_vacancy_selection_uses_14_day_window_and_recommendable_states():
    recent = vacancy("recent", NOW - timedelta(days=5))
    old = vacancy("old", NOW - timedelta(days=20))
    updated_old = vacancy("updated-old", NOW - timedelta(days=30))
    updated_old.lifecycle_status = VacancyLifecycleStatus.UPDATED
    updated_old.last_material_change_at = NOW - timedelta(days=2)
    stale = vacancy("stale", NOW - timedelta(days=1))
    stale.lifecycle_status = VacancyLifecycleStatus.STALE

    selected = select_recent_recommendable_vacancies(
        [old, stale, recent, updated_old], as_of=NOW, lookback_days=14, max_vacancies=50
    )
    assert [row.vacancy_id for row in selected] == ["updated-old", "recent"]


def test_stored_recommendation_freshness_requires_current_lifecycle_and_recent_observation():
    recent = vacancy("recent", NOW - timedelta(days=3))
    recent.last_seen_at = NOW - timedelta(days=2)
    assert is_fresh_for_restored_access(recent, as_of=NOW, max_unseen_days=7)

    recent.lifecycle_status = VacancyLifecycleStatus.CLOSED
    assert not is_fresh_for_restored_access(recent, as_of=NOW, max_unseen_days=7)

    old = vacancy("old", NOW - timedelta(days=30))
    old.last_seen_at = NOW - timedelta(days=8)
    assert not is_fresh_for_restored_access(old, as_of=NOW, max_unseen_days=7)


def test_teaser_is_truthful_and_does_not_reveal_vacancy_details():
    assert "identified 2 recent opportunities" in campaign_teaser_text(2)
    assert "Activate Job Discovery" in campaign_teaser_text(2)
    assert "found" not in campaign_teaser_text(0).lower()
