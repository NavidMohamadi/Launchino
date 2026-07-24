from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from schemas import (
    Alignment, BridgeabilityStatus, Category, CategoryResult, EvidenceQuality,
    ItemResult, MatchConfiguration, MatchResult, NotScoredReason, RequirementType,
    ResultLane, TrainabilityWindow, UnknownReason, ValueStatus,
)


ALIGNMENT_SCORE = {
    Alignment.ALIGNED: 3.0,
    Alignment.POTENTIALLY_ALIGNED: 2.0,
    Alignment.WEAK_ALIGNMENT: 1.0,
    Alignment.MISALIGNED: 0.0,
    Alignment.UNKNOWN: None,
}


def score_ordinal_requirement(candidate_level: Optional[int], required_level: Optional[int]) -> Tuple[Alignment, str]:
    """Current capability alignment only; trainability does not add points."""
    if candidate_level is None or required_level is None:
        return Alignment.UNKNOWN, "Candidate or vacancy level is not specified."
    if candidate_level >= required_level:
        return Alignment.ALIGNED, "Candidate meets or exceeds the stated current level."
    gap = required_level - candidate_level
    if gap == 1:
        return Alignment.WEAK_ALIGNMENT, "Candidate is one level below the stated current requirement."
    return Alignment.MISALIGNED, "Candidate is more than one level below the stated current requirement."


def assess_bridgeability(*, trainability_window: TrainabilityWindow, reviewer_status: BridgeabilityStatus, reviewer_note: Optional[str]) -> tuple[BridgeabilityStatus, str]:
    """Record human-reviewed bridgeability without modifying the current alignment score."""
    if trainability_window in {TrainabilityWindow.NOT_TRAINABLE, TrainabilityWindow.NOT_SPECIFIED}:
        return BridgeabilityStatus.NOT_APPLICABLE, "The vacancy does not define a usable trainability window."
    if reviewer_status == BridgeabilityStatus.NOT_REVIEWED:
        return reviewer_status, "Bridgeability requires human review."
    if not reviewer_note:
        raise ValueError("A bridgeability note is required when a reviewer status is assigned")
    return reviewer_status, reviewer_note


def make_item_result(
    *, talent_id: str, vacancy_id: str, element_id: str, category: Category,
    alignment: Alignment, item_importance: int, requirement_type: RequirementType,
    reason: str, evidence_quality: EvidenceQuality | None = None,
    clarification_required: bool = False,
    unknown_reason: UnknownReason = UnknownReason.REQUIRES_VERIFICATION,
    bridgeability_status: BridgeabilityStatus = BridgeabilityStatus.NOT_APPLICABLE,
    bridgeability_note: Optional[str] = None,
) -> ItemResult:
    value_status = ValueStatus.UNKNOWN if alignment == Alignment.UNKNOWN else ValueStatus.ANSWERED
    critical_review = requirement_type == RequirementType.CRITICAL and alignment in {Alignment.MISALIGNED, Alignment.UNKNOWN}
    return ItemResult(
        talent_id=talent_id, vacancy_id=vacancy_id, element_id=element_id, category=category,
        value_status=value_status, alignment=alignment, score=ALIGNMENT_SCORE[alignment],
        item_importance=item_importance, requirement_type=requirement_type,
        evidence_quality=evidence_quality, reason=reason,
        unknown_reason=unknown_reason if value_status == ValueStatus.UNKNOWN else None,
        clarification_required=clarification_required or value_status == ValueStatus.UNKNOWN,
        human_review_required=critical_review,
        bridgeability_status=bridgeability_status, bridgeability_note=bridgeability_note,
    )


def make_not_scored_item_result(
    *, talent_id: str, vacancy_id: str, element_id: str, category: Category,
    item_importance: int = 1, requirement_type: RequirementType = RequirementType.INFORMATION_ONLY,
    reason: str = "The element was deliberately not activated for this comparison.",
    not_scored_reason: NotScoredReason = NotScoredReason.OUT_OF_SCOPE_BY_DESIGN,
) -> ItemResult:
    return ItemResult(
        talent_id=talent_id, vacancy_id=vacancy_id, element_id=element_id, category=category,
        value_status=ValueStatus.NOT_SCORED, alignment=None, score=None,
        item_importance=item_importance, requirement_type=requirement_type,
        reason=reason, not_scored_reason=not_scored_reason,
    )


def _assign_lane(*, overall_score: Optional[float], overall_coverage: float, critical_flags: List[str], clarification_flags: List[str], config: MatchConfiguration) -> ResultLane:
    if critical_flags:
        return ResultLane.CRITICAL_REVIEW
    if clarification_flags:
        return ResultLane.CLARIFICATION_REQUIRED
    if overall_score is None or overall_coverage < config.minimum_overall_coverage * 100:
        return ResultLane.CLARIFICATION_REQUIRED
    if overall_score >= config.priority_score_threshold:
        return ResultLane.PRIORITY_MATCH
    if overall_score >= config.promising_score_threshold:
        return ResultLane.PROMISING_MATCH
    return ResultLane.LOWER_ALIGNMENT


def aggregate_match(*, talent_id: str, vacancy_id: str, item_results: List[ItemResult], config: MatchConfiguration) -> MatchResult:
    if config.vacancy_id != vacancy_id:
        raise ValueError("MatchConfiguration vacancy_id does not match the match being aggregated")
    by_category: Dict[Category, List[ItemResult]] = defaultdict(list)
    for item in item_results:
        by_category[item.category].append(item)

    category_results: List[CategoryResult] = []
    weighted_score_sum = usable_category_weight = 0.0
    answered_weight_total = active_weight_total = 0.0
    critical_flags: List[str] = []
    clarification_flags: List[str] = []

    for category, weight in config.category_weights.items():
        items = by_category.get(category, [])
        active_items = [i for i in items if i.value_status != ValueStatus.NOT_SCORED]
        answered_items = [i for i in active_items if i.value_status == ValueStatus.ANSWERED]
        not_scored_items = [i for i in items if i.value_status == ValueStatus.NOT_SCORED]
        active_weight = sum(i.item_importance for i in active_items)
        answered_weight = sum(i.item_importance for i in answered_items)
        active_weight_total += active_weight
        answered_weight_total += answered_weight

        category_critical = [i.element_id for i in active_items if i.human_review_required]
        critical_flags.extend(category_critical)
        unknowns = [i.element_id for i in active_items if i.value_status == ValueStatus.UNKNOWN]
        requested_clarifications = [i.element_id for i in active_items if i.clarification_required]
        clarification_flags.extend(unknowns + requested_clarifications)

        coverage = answered_weight / active_weight if active_weight else 0.0
        if answered_weight:
            raw = sum(float(i.score) * i.item_importance for i in answered_items) / (3.0 * answered_weight)
            score_percent = round(raw * 100, 1)
        else:
            score_percent = None

        category_results.append(CategoryResult(
            category=category, score_percent=score_percent,
            coverage_percent=round(coverage * 100, 1), category_weight=weight,
            active_item_count=len(active_items), answered_item_count=len(answered_items),
            not_scored_item_count=len(not_scored_items), critical_issues=len(category_critical),
            unknown_items=len(unknowns),
        ))
        if score_percent is not None and coverage >= config.minimum_category_coverage:
            weighted_score_sum += score_percent * weight
            usable_category_weight += weight

    overall = round(weighted_score_sum / usable_category_weight, 1) if usable_category_weight else None
    overall_coverage = round(100 * answered_weight_total / active_weight_total, 1) if active_weight_total else 0.0
    lane = _assign_lane(
        overall_score=overall, overall_coverage=overall_coverage,
        critical_flags=critical_flags, clarification_flags=clarification_flags, config=config,
    )
    return MatchResult(
        talent_id=talent_id, vacancy_id=vacancy_id,
        overall_score_percent=overall, overall_coverage_percent=overall_coverage,
        category_results=category_results, critical_flags=sorted(set(critical_flags)),
        clarification_flags=sorted(set(clarification_flags)), lane=lane,
        provisional=lane in {ResultLane.CLARIFICATION_REQUIRED, ResultLane.CRITICAL_REVIEW},
    )


LANE_ORDER = {
    ResultLane.PRIORITY_MATCH: 0,
    ResultLane.PROMISING_MATCH: 1,
    ResultLane.CLARIFICATION_REQUIRED: 2,
    ResultLane.CRITICAL_REVIEW: 3,
    ResultLane.LOWER_ALIGNMENT: 4,
}


def rank_match_results(results: List[MatchResult]) -> List[MatchResult]:
    """Sort within operational lanes; no one-dimensional confidence-equivalent list."""
    return sorted(results, key=lambda r: (
        LANE_ORDER[r.lane],
        -(r.overall_score_percent if r.overall_score_percent is not None else -1),
        -r.overall_coverage_percent,
        r.talent_id,
    ))


def group_match_results(results: List[MatchResult]) -> Dict[ResultLane, List[MatchResult]]:
    grouped: Dict[ResultLane, List[MatchResult]] = {lane: [] for lane in ResultLane}
    for result in rank_match_results(results):
        grouped[result.lane].append(result)
    return grouped
