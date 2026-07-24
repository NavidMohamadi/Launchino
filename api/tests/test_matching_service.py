"""Pure-logic tests for api/matching_service.py and api/comparators_dispatch.py.

No database is involved: dictionary/talent/vacancy rows are built in memory
in the same shape matching_service expects from Postgres, so this exercises
the activation + comparator-dispatch + aggregation wiring on top of the
unmodified src/ library without requiring a running Postgres instance.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from schemas import (  # noqa: E402
    Alignment, Category, FitElement, MatchConfiguration, NotScoredReason,
    ResultLane, SharingStatus, SourceType, ValueStatus,
)

from api.matching_service import build_item_results  # noqa: E402
from match_engine import aggregate_match  # noqa: E402


def _element(**overrides) -> FitElement:
    base = dict(
        element_id="ENV-STRUCTURE",
        category=Category.ENV,
        label="Goal and role structure",
        definition="How clearly goals and responsibilities are defined.",
        activation_policy="always",
        candidate_question="q?",
        vacancy_question="q?",
        candidate_value_schema={"scale_id": "env_structure_1_5"},
        vacancy_value_schema={"scale_id": "env_structure_1_5"},
        evidence_rule="rule",
        comparator_key="ordinal_range",
        sharing_status=SharingStatus.CANDIDATE_VISIBLE,
    )
    base.update(overrides)
    return FitElement.model_validate(base)


def _config(**weights) -> MatchConfiguration:
    return MatchConfiguration(vacancy_id="VAC-1", category_weights=weights or {Category.ENV: 100})


def test_ordinal_range_element_scores_aligned():
    element = _element()
    dictionary = {element.element_id: element}
    talent_values = {
        element.element_id: {
            "value": {"preferred_min": 3, "preferred_max": 5, "tolerable_min": 2, "tolerable_max": 5},
            "value_status": "answered",
        }
    }
    vacancy_values = {element.element_id: {"value": {"actual": 4}, "value_status": "answered"}}

    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert len(items) == 1
    assert items[0].alignment == Alignment.ALIGNED
    assert items[0].value_status == ValueStatus.ANSWERED

    result = aggregate_match(talent_id="T-1", vacancy_id="VAC-1", item_results=items, config=_config())
    assert result.overall_score_percent == 100.0
    assert result.lane == ResultLane.PRIORITY_MATCH


def test_missing_vacancy_answer_is_unknown_not_a_guess():
    element = _element()
    dictionary = {element.element_id: element}
    talent_values = {
        element.element_id: {
            "value": {"preferred_min": 3, "preferred_max": 5, "tolerable_min": 2, "tolerable_max": 5},
            "value_status": "answered",
        }
    }
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values={},
    )
    assert items[0].value_status == ValueStatus.UNKNOWN
    assert items[0].unknown_reason.value == "vacancy_not_specified"


def test_vacancy_activated_element_not_scored_when_not_activated():
    element = _element(
        element_id="TEAM-COMM", category=Category.TEAM, activation_policy="vacancy_activated",
        vacancy_value_schema={"activated": "boolean"},
    )
    dictionary = {element.element_id: element}
    vacancy_values = {element.element_id: {"value": {"activated": False}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values={}, vacancy_values=vacancy_values,
    )
    assert items[0].value_status == ValueStatus.NOT_SCORED
    assert items[0].not_scored_reason == NotScoredReason.NOT_ACTIVATED_FOR_VACANCY


def test_candidate_selected_motivation_not_scored_when_not_selected():
    element = _element(
        element_id="MOT-LEARN", category=Category.MOT, activation_policy="candidate_selected",
        candidate_value_schema={"selected": "boolean"},
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {"value": {"selected": False}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values={},
    )
    assert items[0].value_status == ValueStatus.NOT_SCORED
    assert items[0].not_scored_reason == NotScoredReason.NOT_TOP_FIVE


def test_semantic_overlap_always_requests_clarification():
    element = _element(
        element_id="CAREER-PRIMARY-ROLE", category=Category.CAREER, comparator_key="semantic_overlap",
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {"value": {"values": ["Data Analyst"]}, "value_status": "answered"}}
    vacancy_values = {element.element_id: {"value": {"values": ["data analyst"]}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert items[0].alignment == Alignment.ALIGNED
    assert items[0].clarification_required is True
