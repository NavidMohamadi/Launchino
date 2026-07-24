from datetime import date

from canonical_vacancy import canonicalise_raw_vacancy
from source_schemas import RawVacancyRecord, VacancyLifecycleStatus
from vacancy_lifecycle import mark_missing, mark_seen


def profile():
    return canonicalise_raw_vacancy(RawVacancyRecord(
        source_id="greenhouse_public_api", source_record_id="b", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com/jobs/1", external_job_id="1",
        company_name="Example", title="Role", description_text="Description", raw_payload={"id": 1}, trust_level=4,
    ))


def test_missing_transitions_to_stale_then_closed():
    p = profile()
    p = mark_missing(p, stale_after_polls=2, close_after_polls=4)
    assert p.lifecycle_status == VacancyLifecycleStatus.ACTIVE
    p = mark_missing(p, stale_after_polls=2, close_after_polls=4)
    assert p.lifecycle_status == VacancyLifecycleStatus.STALE
    p = mark_missing(p, stale_after_polls=2, close_after_polls=3)
    assert p.lifecycle_status == VacancyLifecycleStatus.CLOSED


def test_seen_with_change_marks_updated():
    p = profile()
    updated = mark_seen(p, content_hash="different")
    assert updated.lifecycle_status == VacancyLifecycleStatus.UPDATED
    assert updated.version == 2


def test_closed_vacancy_reappearing_unchanged_becomes_active():
    from datetime import datetime, timezone

    p = profile()
    p.lifecycle_status = VacancyLifecycleStatus.CLOSED
    p.closed_reason = "valid_through_expired"
    p.closed_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
    seen_at = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)

    reopened = mark_seen(p, content_hash=p.content_hash, seen_at=seen_at)

    assert reopened.lifecycle_status == VacancyLifecycleStatus.ACTIVE
    assert reopened.reopened_at == seen_at
    assert reopened.reopened_reason == "observed_again_after_closure"
    assert reopened.closed_reason is None
    assert reopened.closed_at is None


def test_archived_vacancy_is_not_automatically_reopened():
    p = profile()
    p.lifecycle_status = VacancyLifecycleStatus.ARCHIVED
    observed = mark_seen(p, content_hash=p.content_hash)
    assert observed.lifecycle_status == VacancyLifecycleStatus.ARCHIVED
