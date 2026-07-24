from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Sequence
from uuid import uuid4

from job_discovery_access import (
    JobDiscoveryBackfillPolicy,
    JobDiscoveryEntitlementService,
    PreliminaryCampaignEligibilityService,
    PreliminaryCampaignPolicy,
    is_fresh_for_restored_access,
    select_recent_recommendable_vacancies,
    vacancy_recency_at,
)
from job_recommendations import LANE_RANK, build_recommendation, is_recommendable
from schemas import MatchResult, ResultLane, Talent
from source_schemas import (
    CanonicalVacancyProfile,
    JobDiscoveryBatchMetrics,
    JobDiscoveryRunType,
    JobRecommendation,
    PreliminaryOpportunitySignal,
)


DeterministicMatcher = Callable[[Talent, CanonicalVacancyProfile], MatchResult]
ExplanationGenerator = Callable[[Talent, MatchResult, CanonicalVacancyProfile], str]
Clock = Callable[[], datetime]


@dataclass
class JobDiscoveryPipelineOutput:
    recommendations: List[JobRecommendation]
    preliminary_signals: List[PreliminaryOpportunitySignal]
    metrics: JobDiscoveryBatchMetrics


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _match_sort_key(match: MatchResult, profile: CanonicalVacancyProfile) -> tuple:
    return (
        LANE_RANK[match.lane],
        -(match.overall_score_percent if match.overall_score_percent is not None else -1),
        -match.overall_coverage_percent,
        -vacancy_recency_at(profile).timestamp(),
        profile.vacancy_id,
    )


def run_full_job_discovery_cycle(
    *,
    talents: Iterable[Talent],
    vacancies: Iterable[CanonicalVacancyProfile],
    deterministic_matcher: DeterministicMatcher,
    explanation_generator: ExplanationGenerator,
    as_of: datetime,
    entitlement_service: JobDiscoveryEntitlementService | None = None,
    max_recommendations_per_talent: int = 10,
    max_ai_explanations_per_talent: int = 5,
    access_clock: Clock | None = None,
    run_type: JobDiscoveryRunType = JobDiscoveryRunType.FULL,
) -> JobDiscoveryPipelineOutput:
    """Run the paid Job Discovery path only for effectively active talents.

    Subscription state is checked before deterministic matching and again before
    each expensive AI explanation call. The deterministic matching engine itself
    remains subscription-unaware.
    """
    if max_recommendations_per_talent < 1:
        raise ValueError("max_recommendations_per_talent must be positive")
    if not 0 <= max_ai_explanations_per_talent <= max_recommendations_per_talent:
        raise ValueError("max_ai_explanations_per_talent must be within the recommendation cap")

    service = entitlement_service or JobDiscoveryEntitlementService()
    clock = access_clock or _default_clock
    talent_list = list(talents)
    vacancy_list = [vacancy for vacancy in vacancies if is_recommendable(vacancy)]
    selected_talents = service.select_active_talents(talent_list, as_of=as_of)

    metrics = JobDiscoveryBatchMetrics(
        run_type=run_type,
        started_at=as_of,
        candidates_considered=len(talent_list),
        candidates_included=len(selected_talents),
        candidates_skipped=len(talent_list) - len(selected_talents),
        vacancies_considered=len(vacancy_list),
    )
    recommendations: List[JobRecommendation] = []

    for talent in selected_talents:
        candidate_matches: List[tuple[MatchResult, CanonicalVacancyProfile]] = []
        for vacancy in vacancy_list:
            match = deterministic_matcher(talent, vacancy)
            if match.talent_id != talent.talent_id or match.vacancy_id != vacancy.vacancy_id:
                raise ValueError("Matcher returned a result for the wrong talent or vacancy")
            metrics.deterministic_matches_run += 1
            candidate_matches.append((match, vacancy))

        candidate_matches.sort(key=lambda pair: _match_sort_key(pair[0], pair[1]))
        candidate_matches = candidate_matches[:max_recommendations_per_talent]

        for index, (match, vacancy) in enumerate(candidate_matches):
            # Recheck immediately before the potentially expensive explanation
            # and before storing a candidate-facing recommendation.
            if not service.has_active_access(talent, as_of=clock()):
                break

            explanation = None
            if index < max_ai_explanations_per_talent:
                explanation = explanation_generator(talent, match, vacancy)
                metrics.ai_explanations_generated += 1

            recommendations.append(
                build_recommendation(match, vacancy, explanation=explanation)
            )
            metrics.recommendations_created += 1

    return JobDiscoveryPipelineOutput(
        recommendations=recommendations,
        preliminary_signals=[],
        metrics=metrics,
    )


def run_preliminary_campaign_cycle(
    *,
    talents: Iterable[Talent],
    vacancies: Iterable[CanonicalVacancyProfile],
    deterministic_matcher: DeterministicMatcher,
    as_of: datetime,
    eligibility_service: PreliminaryCampaignEligibilityService | None = None,
    policy: PreliminaryCampaignPolicy | None = None,
) -> JobDiscoveryPipelineOutput:
    """Run controlled, deterministic-only opportunity detection for campaigns.

    No AI explanation is generated, no JobRecommendation is created, and the
    signal itself is not visible to the candidate as vacancy details or a score.
    """
    policy = policy or PreliminaryCampaignPolicy()
    eligibility = eligibility_service or PreliminaryCampaignEligibilityService(policy=policy)
    talent_list = list(talents)
    selected_talents = eligibility.select_eligible_talents(talent_list, as_of=as_of)
    vacancy_list = select_recent_recommendable_vacancies(
        vacancies,
        as_of=as_of,
        lookback_days=policy.lookback_days,
        max_vacancies=policy.max_vacancies,
    )

    metrics = JobDiscoveryBatchMetrics(
        run_type=JobDiscoveryRunType.PRELIMINARY_CAMPAIGN,
        started_at=as_of,
        candidates_considered=len(talent_list),
        candidates_included=len(selected_talents),
        candidates_skipped=len(talent_list) - len(selected_talents),
        vacancies_considered=len(vacancy_list),
    )
    signals: List[PreliminaryOpportunitySignal] = []

    for talent in selected_talents:
        qualifying: List[tuple[MatchResult, CanonicalVacancyProfile]] = []
        for vacancy in vacancy_list:
            match = deterministic_matcher(talent, vacancy)
            metrics.deterministic_matches_run += 1
            if (
                match.lane in {ResultLane.PRIORITY_MATCH, ResultLane.PROMISING_MATCH}
                and match.overall_score_percent is not None
                and match.overall_score_percent >= policy.minimum_score_percent
                and match.overall_coverage_percent >= policy.minimum_coverage_percent
            ):
                qualifying.append((match, vacancy))

        qualifying.sort(key=lambda pair: _match_sort_key(pair[0], pair[1]))
        for match, vacancy in qualifying[: policy.max_signals_per_talent]:
            signals.append(
                PreliminaryOpportunitySignal(
                    signal_id=str(uuid4()),
                    talent_id=talent.talent_id,
                    vacancy_id=vacancy.vacancy_id,
                    result_lane=match.lane,
                    overall_score_percent=match.overall_score_percent,
                    overall_coverage_percent=match.overall_coverage_percent,
                    detected_at=as_of,
                )
            )
            metrics.preliminary_signals_created += 1

    return JobDiscoveryPipelineOutput(
        recommendations=[],
        preliminary_signals=signals,
        metrics=metrics,
    )


def run_subscription_backfill(
    *,
    talent: Talent,
    vacancies: Iterable[CanonicalVacancyProfile],
    deterministic_matcher: DeterministicMatcher,
    explanation_generator: ExplanationGenerator,
    as_of: datetime,
    entitlement_service: JobDiscoveryEntitlementService | None = None,
    policy: JobDiscoveryBackfillPolicy | None = None,
    access_clock: Clock | None = None,
) -> JobDiscoveryPipelineOutput:
    """Give a new or renewed subscriber immediate value from recent vacancies."""
    policy = policy or JobDiscoveryBackfillPolicy()
    selected_vacancies = select_recent_recommendable_vacancies(
        vacancies,
        as_of=as_of,
        lookback_days=policy.lookback_days,
        max_vacancies=policy.max_vacancies,
    )
    return run_full_job_discovery_cycle(
        talents=[talent],
        vacancies=selected_vacancies,
        deterministic_matcher=deterministic_matcher,
        explanation_generator=explanation_generator,
        as_of=as_of,
        entitlement_service=entitlement_service,
        max_recommendations_per_talent=policy.max_recommendations,
        max_ai_explanations_per_talent=policy.max_ai_explanations,
        access_clock=access_clock,
        run_type=JobDiscoveryRunType.SUBSCRIPTION_BACKFILL,
    )


def visible_recommendations_for_talent(
    *,
    talent: Talent,
    recommendations: Iterable[JobRecommendation],
    profiles: Dict[str, CanonicalVacancyProfile],
    as_of: datetime,
    entitlement_service: JobDiscoveryEntitlementService | None = None,
    max_unseen_days: int = 7,
) -> List[JobRecommendation]:
    """Hide on expiry; restore fresh, still-active stored records after renewal."""
    service = entitlement_service or JobDiscoveryEntitlementService()
    if not service.can_view_recommendations(talent, as_of=as_of):
        return []

    visible = []
    for recommendation in recommendations:
        if recommendation.talent_id != talent.talent_id:
            continue
        profile = profiles.get(recommendation.vacancy_id)
        if profile is None:
            continue
        if is_fresh_for_restored_access(
            profile,
            as_of=as_of,
            max_unseen_days=max_unseen_days,
        ):
            visible.append(recommendation)

    visible.sort(
        key=lambda recommendation: _match_sort_key(
            recommendation.match_result,
            profiles[recommendation.vacancy_id],
        )
    )
    return visible
