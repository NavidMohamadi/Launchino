"""Runs a match by loading stored talent/vacancy element values and handing
them to the unmodified src/ activation + comparator + match_engine functions.

This module owns no scoring logic of its own beyond dispatch (comparators_dispatch)
and persistence; activation, alignment scoring, aggregation, and lane
assignment all come straight from src/.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from activation import resolve_scope
from match_engine import _assign_lane, aggregate_match, make_item_result, make_not_scored_item_result

from api.comparators_dispatch import compare_answered_values
from schemas import (
    ActivationPolicy, Alignment, FitElement, ItemResult, MatchConfiguration,
    MatchResult, RequirementType, ResultLane, UnknownReason, ValueStatus,
)


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def load_dictionary(conn: Connection) -> Dict[str, FitElement]:
    rows = conn.execute(text("select * from fit_element where active = true")).mappings().all()
    dictionary: Dict[str, FitElement] = {}
    for row in rows:
        data = dict(row)
        data["candidate_value_schema"] = _as_json(data["candidate_value_schema"])
        data["vacancy_value_schema"] = _as_json(data["vacancy_value_schema"])
        dictionary[data["element_id"]] = FitElement.model_validate(data)
    return dictionary


def load_talent_values(conn: Connection, talent_id: UUID) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select distinct on (element_id)
                element_id, value, value_status, unknown_reason, not_scored_reason,
                source_type, last_confirmed_at, shareable_with_employer
            from talent_element_value
            where talent_id = :talent_id
            order by element_id, record_version desc
            """
        ),
        {"talent_id": str(talent_id)},
    ).mappings().all()
    return {r["element_id"]: {**dict(r), "value": _as_json(r["value"])} for r in rows}


def load_vacancy_values(conn: Connection, vacancy_id: UUID) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select element_id, value, value_status, unknown_reason, not_scored_reason,
                   source_type, item_importance, requirement_type, trainability_window,
                   last_confirmed_at
            from vacancy_element_value
            where vacancy_id = :vacancy_id
            """
        ),
        {"vacancy_id": str(vacancy_id)},
    ).mappings().all()
    return {r["element_id"]: {**dict(r), "value": _as_json(r["value"])} for r in rows}


def get_talent(conn: Connection, talent_id: UUID) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text("select * from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).mappings().first()
    return dict(row) if row else None


def get_vacancy(conn: Connection, vacancy_id: UUID) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text("select * from vacancy where vacancy_id = :vacancy_id"), {"vacancy_id": str(vacancy_id)}
    ).mappings().first()
    return dict(row) if row else None


def build_item_results(
    *,
    talent_id: UUID,
    vacancy_id: UUID,
    dictionary: Dict[str, FitElement],
    talent_values: Dict[str, Dict[str, Any]],
    vacancy_values: Dict[str, Dict[str, Any]],
) -> List[ItemResult]:
    items: List[ItemResult] = []
    for element_id, element in dictionary.items():
        talent_row = talent_values.get(element_id)
        vacancy_row = vacancy_values.get(element_id)

        candidate_selected = bool(
            element.activation_policy == ActivationPolicy.CANDIDATE_SELECTED
            and talent_row
            and talent_row["value"].get("selected", False)
        )
        vacancy_activated = bool(
            element.activation_policy == ActivationPolicy.VACANCY_ACTIVATED
            and vacancy_row
            and vacancy_row["value"].get("activated", False)
        )
        candidate_answered = bool(talent_row and talent_row["value_status"] == ValueStatus.ANSWERED.value)
        vacancy_answered = bool(vacancy_row and vacancy_row["value_status"] == ValueStatus.ANSWERED.value)

        if not vacancy_answered:
            unknown_reason = UnknownReason.VACANCY_NOT_SPECIFIED
        elif not candidate_answered:
            unknown_reason = UnknownReason.CANDIDATE_NOT_ANSWERED
        else:
            unknown_reason = UnknownReason.REQUIRES_VERIFICATION

        resolution = resolve_scope(
            element,
            candidate_selected=candidate_selected,
            vacancy_activated=vacancy_activated,
            candidate_answered=candidate_answered,
            vacancy_answered=vacancy_answered,
            unknown_reason=unknown_reason,
        )

        item_importance = int(vacancy_row.get("item_importance", 3)) if vacancy_row else 3
        requirement_type = (
            RequirementType(vacancy_row.get("requirement_type", RequirementType.IMPORTANT.value))
            if vacancy_row else RequirementType.IMPORTANT
        )

        if resolution.value_status == ValueStatus.NOT_SCORED:
            items.append(
                make_not_scored_item_result(
                    talent_id=str(talent_id), vacancy_id=str(vacancy_id), element_id=element_id,
                    category=element.category, reason=resolution.explanation,
                    not_scored_reason=resolution.not_scored_reason,
                )
            )
        elif resolution.value_status == ValueStatus.UNKNOWN:
            items.append(
                make_item_result(
                    talent_id=str(talent_id), vacancy_id=str(vacancy_id), element_id=element_id,
                    category=element.category, alignment=Alignment.UNKNOWN,
                    item_importance=item_importance, requirement_type=requirement_type,
                    reason=resolution.explanation, unknown_reason=resolution.unknown_reason,
                )
            )
        else:
            alignment, reason, clarification_required = compare_answered_values(
                element, talent_row["value"], vacancy_row["value"]
            )
            items.append(
                make_item_result(
                    talent_id=str(talent_id), vacancy_id=str(vacancy_id), element_id=element_id,
                    category=element.category, alignment=alignment,
                    item_importance=item_importance, requirement_type=requirement_type,
                    reason=reason, clarification_required=clarification_required,
                )
            )
    return items


def _flag_categories_with_no_data(result: MatchResult, *, config: MatchConfiguration) -> MatchResult:
    """Post-aggregation check -- deliberately kept out of match_engine.py (frozen
    since v1.2.1, see PROJECT_NOTES.md), not a change to aggregate_match itself.

    aggregate_match() silently excludes a category's configured weight from the
    overall score whenever that category has zero active elements (e.g. CAP/TASK
    today -- the Fit Dictionary has no seeded elements for either) -- the score
    gets renormalized over the remaining categories with no signal that anything
    was left out. This surfaces that gap the same way the system already surfaces
    any other incomplete data: as a clarification_flags entry, which _assign_lane
    (unmodified, imported from match_engine) already treats as forcing
    CLARIFICATION_REQUIRED -- not a new signal type.
    """
    missing_data_flags = [
        f"{cr.category.value}: no data available for this category"
        for cr in result.category_results
        if cr.category_weight > 0 and cr.active_item_count == 0
    ]
    if not missing_data_flags:
        return result

    clarification_flags = sorted(set(result.clarification_flags) | set(missing_data_flags))
    lane = _assign_lane(
        overall_score=result.overall_score_percent, overall_coverage=result.overall_coverage_percent,
        critical_flags=result.critical_flags, clarification_flags=clarification_flags, config=config,
    )
    return result.model_copy(update={
        "clarification_flags": clarification_flags,
        "lane": lane,
        "provisional": lane in {ResultLane.CLARIFICATION_REQUIRED, ResultLane.CRITICAL_REVIEW},
    })


def persist_match_run(
    conn: Connection, *, vacancy_id: UUID, config: MatchConfiguration, approved_by: Optional[str], weighting_mode: str,
) -> UUID:
    match_run_id = uuid.uuid4()
    weight_configuration = {category.value: weight for category, weight in config.category_weights.items()}
    threshold_configuration = {
        "minimum_overall_coverage": config.minimum_overall_coverage,
        "minimum_category_coverage": config.minimum_category_coverage,
        "priority_score_threshold": config.priority_score_threshold,
        "promising_score_threshold": config.promising_score_threshold,
    }
    approved_at = datetime.now(timezone.utc) if approved_by else None
    conn.execute(
        text(
            """
            insert into match_run (
                match_run_id, vacancy_id, algorithm_version, weighting_mode, weight_configuration,
                threshold_configuration, approved_by, approved_at
            ) values (
                :match_run_id, :vacancy_id, :algorithm_version, :weighting_mode, cast(:weight_configuration as jsonb),
                cast(:threshold_configuration as jsonb), :approved_by, :approved_at
            )
            """
        ),
        {
            "match_run_id": str(match_run_id),
            "vacancy_id": str(vacancy_id),
            "algorithm_version": config.algorithm_version,
            "weighting_mode": weighting_mode,
            "weight_configuration": json.dumps(weight_configuration),
            "threshold_configuration": json.dumps(threshold_configuration),
            "approved_by": approved_by,
            "approved_at": approved_at,
        },
    )
    return match_run_id


def persist_item_results(conn: Connection, *, match_run_id: UUID, item_results: List[ItemResult]) -> None:
    for item in item_results:
        conn.execute(
            text(
                """
                insert into match_item_result (
                    match_run_id, talent_id, element_id, value_status, alignment, score,
                    unknown_reason, not_scored_reason, reason, requirement_type,
                    clarification_required, human_review_required, bridgeability_status,
                    bridgeability_note
                ) values (
                    :match_run_id, :talent_id, :element_id, :value_status, :alignment, :score,
                    :unknown_reason, :not_scored_reason, :reason, :requirement_type,
                    :clarification_required, :human_review_required, :bridgeability_status,
                    :bridgeability_note
                )
                """
            ),
            {
                "match_run_id": str(match_run_id),
                "talent_id": item.talent_id,
                "element_id": item.element_id,
                "value_status": item.value_status.value,
                "alignment": item.alignment.value if item.alignment else None,
                "score": item.score,
                "unknown_reason": item.unknown_reason.value if item.unknown_reason else None,
                "not_scored_reason": item.not_scored_reason.value if item.not_scored_reason else None,
                "reason": item.reason,
                "requirement_type": item.requirement_type.value,
                "clarification_required": item.clarification_required,
                "human_review_required": item.human_review_required,
                "bridgeability_status": item.bridgeability_status.value,
                "bridgeability_note": item.bridgeability_note,
            },
        )


def persist_match_summary(conn: Connection, *, match_run_id: UUID, result: MatchResult) -> None:
    category_results = [cr.model_dump(mode="json") for cr in result.category_results]
    conn.execute(
        text(
            """
            insert into match_summary (
                match_run_id, talent_id, overall_score, overall_coverage, category_results,
                result_lane, critical_flags, clarification_flags, provisional, reviewer_status
            ) values (
                :match_run_id, :talent_id, :overall_score, :overall_coverage, cast(:category_results as jsonb),
                :result_lane, cast(:critical_flags as jsonb), cast(:clarification_flags as jsonb),
                :provisional, 'pending'
            )
            """
        ),
        {
            "match_run_id": str(match_run_id),
            "talent_id": result.talent_id,
            "overall_score": result.overall_score_percent,
            "overall_coverage": result.overall_coverage_percent,
            "category_results": json.dumps(category_results),
            "result_lane": result.lane.value,
            "critical_flags": json.dumps(result.critical_flags),
            "clarification_flags": json.dumps(result.clarification_flags),
            "provisional": result.provisional,
        },
    )


def run_match(
    conn: Connection, *, vacancy_id: UUID, talent_ids: List[UUID], config: MatchConfiguration,
    approved_by: Optional[str], weighting_mode: str,
) -> Dict[str, Any]:
    dictionary = load_dictionary(conn)
    vacancy_values = load_vacancy_values(conn, vacancy_id)
    match_run_id = persist_match_run(
        conn, vacancy_id=vacancy_id, config=config, approved_by=approved_by, weighting_mode=weighting_mode,
    )

    results: List[MatchResult] = []
    for talent_id in talent_ids:
        talent_values = load_talent_values(conn, talent_id)
        item_results = build_item_results(
            talent_id=talent_id, vacancy_id=vacancy_id, dictionary=dictionary,
            talent_values=talent_values, vacancy_values=vacancy_values,
        )
        result = aggregate_match(
            talent_id=str(talent_id), vacancy_id=str(vacancy_id), item_results=item_results, config=config
        )
        result = _flag_categories_with_no_data(result, config=config)
        persist_item_results(conn, match_run_id=match_run_id, item_results=item_results)
        persist_match_summary(conn, match_run_id=match_run_id, result=result)
        results.append(result)

    return {"match_run_id": match_run_id, "vacancy_id": vacancy_id, "results": results}
