from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from schemas import MatchResult, ResultLane
from source_schemas import (
    CanonicalVacancyProfile,
    JobRecommendation,
    VacancyLifecycleStatus,
    VerificationStatus,
    WeightingMode,
)


LANE_RANK = {
    ResultLane.PRIORITY_MATCH: 0,
    ResultLane.PROMISING_MATCH: 1,
    ResultLane.CLARIFICATION_REQUIRED: 2,
    ResultLane.CRITICAL_REVIEW: 3,
    ResultLane.LOWER_ALIGNMENT: 4,
}

VERIFICATION_RANK = {
    VerificationStatus.COMPANY_VALIDATED: 0,
    VerificationStatus.HUMAN_REVIEWED: 1,
    VerificationStatus.SOURCE_VERIFIED: 2,
    VerificationStatus.AUTO_EXTRACTED: 3,
}

# Recommendation eligibility is explicit rather than assumed by an upstream
# query. STALE, CLOSED and ARCHIVED vacancies are retained for audit/history but
# are not shown as current opportunities.
RECOMMENDABLE_STATUSES = {
    VacancyLifecycleStatus.ACTIVE,
    VacancyLifecycleStatus.UPDATED,
}


def is_recommendable(profile: CanonicalVacancyProfile) -> bool:
    return profile.lifecycle_status in RECOMMENDABLE_STATUSES


def build_recommendation(
    match: MatchResult,
    profile: CanonicalVacancyProfile,
    *,
    explanation: Optional[str] = None,
) -> JobRecommendation:
    if not is_recommendable(profile):
        raise ValueError(
            f"Vacancy {profile.vacancy_id} is not recommendable in lifecycle state "
            f"{profile.lifecycle_status.value}"
        )
    public_provisional = (
        profile.weighting_mode != WeightingMode.COMPANY_CONFIRMED
        or profile.verification_status != VerificationStatus.COMPANY_VALIDATED
    )
    score = "unknown" if match.overall_score_percent is None else f"{match.overall_score_percent:.1f}%"
    explanation = explanation or (
        f"Preliminary alignment {score} with {match.overall_coverage_percent:.1f}% coverage. "
        f"Lane: {match.lane.value}. Verification: {profile.verification_status.value}."
    )
    return JobRecommendation(
        talent_id=match.talent_id,
        vacancy_id=profile.vacancy_id,
        match_result=match,
        vacancy_verification_status=profile.verification_status,
        weighting_mode=profile.weighting_mode,
        source_url=profile.primary_source_url,
        provisional_public_match=public_provisional,
        freshness_status=profile.lifecycle_status,
        explanation=explanation,
    )


def rank_jobs_for_talent(
    talent_id: str,
    matches: Iterable[MatchResult],
    profiles: Dict[str, CanonicalVacancyProfile],
) -> List[JobRecommendation]:
    recommendations = []
    for match in matches:
        profile = profiles.get(match.vacancy_id)
        if match.talent_id != talent_id or profile is None or not is_recommendable(profile):
            continue
        recommendations.append(build_recommendation(match, profile))

    return sorted(
        recommendations,
        key=lambda rec: (
            LANE_RANK[rec.match_result.lane],
            VERIFICATION_RANK[rec.vacancy_verification_status],
            rec.provisional_public_match,
            -(rec.match_result.overall_score_percent or -1),
            -rec.match_result.overall_coverage_percent,
            -profiles[rec.vacancy_id].last_material_change_at.timestamp(),
            rec.vacancy_id,
        ),
    )
