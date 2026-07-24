from __future__ import annotations

from datetime import date, datetime, timezone

from source_schemas import CanonicalVacancyProfile, VacancyLifecycleStatus


def mark_seen(
    profile: CanonicalVacancyProfile,
    *,
    content_hash: str,
    seen_at: datetime | None = None,
    increment_version: bool = True,
) -> CanonicalVacancyProfile:
    """Record a direct source observation.

    A direct observation reactivates a previously CLOSED vacancy, even when the
    content is unchanged. ARCHIVED is a deliberate human state and is never
    reopened automatically.
    """
    seen_at = seen_at or datetime.now(timezone.utc)
    updated = profile.model_copy(deep=True)
    previous_status = profile.lifecycle_status
    changed = content_hash != profile.content_hash

    updated.last_seen_at = seen_at
    updated.missing_poll_count = 0

    if previous_status == VacancyLifecycleStatus.ARCHIVED:
        return updated

    if changed:
        updated.content_hash = content_hash
        updated.last_material_change_at = seen_at
        if increment_version:
            updated.version += 1
        updated.lifecycle_status = VacancyLifecycleStatus.UPDATED
    else:
        updated.lifecycle_status = VacancyLifecycleStatus.ACTIVE

    if previous_status == VacancyLifecycleStatus.CLOSED:
        updated.reopened_at = seen_at
        updated.reopened_reason = "observed_again_after_closure"
        updated.closed_at = None
        updated.closed_reason = None

    return updated


def mark_missing(
    profile: CanonicalVacancyProfile,
    *,
    today: date | None = None,
    observed_at: datetime | None = None,
    stale_after_polls: int = 2,
    close_after_polls: int = 4,
) -> CanonicalVacancyProfile:
    today = today or date.today()
    observed_at = observed_at or datetime.now(timezone.utc)
    updated = profile.model_copy(deep=True)

    if updated.lifecycle_status == VacancyLifecycleStatus.ARCHIVED:
        return updated

    updated.missing_poll_count += 1
    close_reason = None
    if profile.valid_through and profile.valid_through < today:
        close_reason = "valid_through_expired"
    elif updated.missing_poll_count >= close_after_polls:
        close_reason = "missing_poll_threshold"

    if close_reason:
        updated.lifecycle_status = VacancyLifecycleStatus.CLOSED
        updated.closed_reason = close_reason
        updated.closed_at = updated.closed_at or observed_at
    elif updated.missing_poll_count >= stale_after_polls:
        updated.lifecycle_status = VacancyLifecycleStatus.STALE
    return updated


def archive(profile: CanonicalVacancyProfile) -> CanonicalVacancyProfile:
    updated = profile.model_copy(deep=True)
    updated.lifecycle_status = VacancyLifecycleStatus.ARCHIVED
    return updated
