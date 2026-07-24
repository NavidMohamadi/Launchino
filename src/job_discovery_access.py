from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, List, Sequence

from job_recommendations import is_recommendable
from schemas import JobDiscoverySubscription, Talent
from source_schemas import CanonicalVacancyProfile


class JobDiscoveryAccessError(ValueError):
    pass


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise JobDiscoveryAccessError("Access-control timestamps must be timezone-aware")
    return value


@dataclass(frozen=True)
class JobDiscoveryBackfillPolicy:
    lookback_days: int = 14
    max_vacancies: int = 50
    max_recommendations: int = 10
    max_ai_explanations: int = 5

    def __post_init__(self) -> None:
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be at least 1")
        if self.max_vacancies < 1:
            raise ValueError("max_vacancies must be at least 1")
        if self.max_recommendations < 1:
            raise ValueError("max_recommendations must be at least 1")
        if not 0 <= self.max_ai_explanations <= self.max_recommendations:
            raise ValueError("max_ai_explanations must be between 0 and max_recommendations")


@dataclass(frozen=True)
class PreliminaryCampaignPolicy:
    lookback_days: int = 14
    max_vacancies: int = 50
    max_signals_per_talent: int = 3
    minimum_score_percent: float = 70.0
    minimum_coverage_percent: float = 70.0
    eligible_profile_statuses: frozenset[str] = frozenset({"complete", "active", "ready"})

    def __post_init__(self) -> None:
        if self.lookback_days < 1 or self.max_vacancies < 1 or self.max_signals_per_talent < 1:
            raise ValueError("Campaign limits must be positive")
        if not 0 <= self.minimum_score_percent <= 100:
            raise ValueError("minimum_score_percent must be between 0 and 100")
        if not 0 <= self.minimum_coverage_percent <= 100:
            raise ValueError("minimum_coverage_percent must be between 0 and 100")


class JobDiscoveryEntitlementService:
    """Single source of truth for effective Job Discovery access.

    ACTIVE with a null expiry is deliberately valid for the initial MVP and
    remains active until SHEXON changes the status. A past expiry always blocks
    access even if a delayed billing process has not yet changed the status.
    """

    def has_active_access(self, talent: Talent, *, as_of: datetime) -> bool:
        as_of = _require_aware(as_of)
        if talent.job_discovery_subscription != JobDiscoverySubscription.ACTIVE:
            return False
        if talent.subscription_expires_at is None:
            return True
        return _require_aware(talent.subscription_expires_at) > as_of

    def select_active_talents(
        self,
        talents: Iterable[Talent],
        *,
        as_of: datetime,
    ) -> List[Talent]:
        return [talent for talent in talents if self.has_active_access(talent, as_of=as_of)]

    def can_view_recommendations(self, talent: Talent, *, as_of: datetime) -> bool:
        return self.has_active_access(talent, as_of=as_of)


class PreliminaryCampaignEligibilityService:
    """Eligibility for low-cost, deterministic non-subscriber campaign matching.

    This is intentionally separate from subscription entitlement. Campaign
    eligibility never grants access to vacancy details, scores or AI-generated
    explanations.
    """

    def __init__(
        self,
        entitlement_service: JobDiscoveryEntitlementService | None = None,
        policy: PreliminaryCampaignPolicy | None = None,
    ) -> None:
        self.entitlement_service = entitlement_service or JobDiscoveryEntitlementService()
        self.policy = policy or PreliminaryCampaignPolicy()

    def is_eligible(self, talent: Talent, *, as_of: datetime) -> bool:
        if self.entitlement_service.has_active_access(talent, as_of=as_of):
            return False
        return (
            talent.job_discovery_campaign_opt_in
            and talent.profile_status.lower() in self.policy.eligible_profile_statuses
        )

    def select_eligible_talents(
        self,
        talents: Iterable[Talent],
        *,
        as_of: datetime,
    ) -> List[Talent]:
        return [talent for talent in talents if self.is_eligible(talent, as_of=as_of)]


def vacancy_recency_at(profile: CanonicalVacancyProfile) -> datetime:
    """Return the best available timestamp for recent-vacancy selection."""
    candidates = [profile.first_seen_at, profile.last_material_change_at]
    if profile.date_posted is not None:
        candidates.append(datetime.combine(profile.date_posted, time.min, tzinfo=timezone.utc))
    return max(_require_aware(value) for value in candidates)


def select_recent_recommendable_vacancies(
    profiles: Iterable[CanonicalVacancyProfile],
    *,
    as_of: datetime,
    lookback_days: int = 14,
    max_vacancies: int = 50,
) -> List[CanonicalVacancyProfile]:
    """Select active/updated vacancies first seen, posted or changed recently."""
    as_of = _require_aware(as_of)
    cutoff = as_of - timedelta(days=lookback_days)
    eligible = [
        profile
        for profile in profiles
        if is_recommendable(profile) and vacancy_recency_at(profile) >= cutoff
    ]
    eligible.sort(key=lambda profile: (vacancy_recency_at(profile), profile.vacancy_id), reverse=True)
    return eligible[:max_vacancies]


def is_fresh_for_restored_access(
    profile: CanonicalVacancyProfile,
    *,
    as_of: datetime,
    max_unseen_days: int = 7,
) -> bool:
    """Defence-in-depth check before resurfacing a stored recommendation."""
    as_of = _require_aware(as_of)
    return (
        is_recommendable(profile)
        and _require_aware(profile.last_seen_at) >= as_of - timedelta(days=max_unseen_days)
    )


def campaign_teaser_text(signal_count: int) -> str:
    if signal_count < 1:
        return "Unlock proactive vacancy discovery and personalised match recommendations."
    noun = "opportunity" if signal_count == 1 else "opportunities"
    pronoun = "it" if signal_count == 1 else "them"
    return (
        f"We identified {signal_count} recent {noun} that may fit your profile. "
        f"Activate Job Discovery to revalidate {pronoun} and view the vacancy details and personalised analysis."
    )
