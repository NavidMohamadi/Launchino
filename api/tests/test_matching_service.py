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


# -- v3 redesign (see PROJECT_NOTES.md) -- Family 1/2/3 continuous scores end
# to end through build_item_results, Family 4 ESCO/NACE structured matching,
# and Family 5's full exclusion from matching. --

def test_ordinal_distance_continuous_score_flows_through_to_item_score():
    element = _element(
        element_id="ENV-PRECISION", comparator_key="ordinal_distance",
        candidate_value_schema={"level": "integer 1..5"}, vacancy_value_schema={"required_level": "integer 1..5"},
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {"value": {"level": 3}, "value_status": "answered"}}
    vacancy_values = {element.element_id: {"value": {"required_level": 4}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    # distance 1 -> 80% -> 2.4 on the 0-3 scale; 80% buckets to POTENTIALLY_ALIGNED
    # (boundary with ALIGNED is 83.335%, the midpoint between the old 100/66.7 anchors)
    assert items[0].score == 2.4
    assert items[0].alignment == Alignment.POTENTIALLY_ALIGNED


def test_motivation_preferred_minimum_continuous_score_flows_through():
    element = _element(
        element_id="MOT-CHALLENGE", category=Category.MOT, comparator_key="motivation_preferred_minimum",
        activation_policy="candidate_selected",
        candidate_value_schema={"selected": "boolean", "preferred_level": "integer", "minimum_acceptable_level": "integer"},
        vacancy_value_schema={"actual_level": "integer"},
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {
        "value": {"selected": True, "preferred_level": 5, "minimum_acceptable_level": 2}, "value_status": "answered",
    }}
    vacancy_values = {element.element_id: {"value": {"actual_level": 4}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    # actual=4 clears minimum=2; |4-5|=1 -> 100-15=85% -> 2.55 on the 0-3 scale
    assert items[0].score == 2.55


def test_esco_occupation_pick_exact_match_is_aligned():
    element = _element(
        element_id="CAREER-PRIMARY-ROLE", category=Category.CAREER, comparator_key="esco_occupation_pick",
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {
        "value": {"occupation": {"esco_uri": "http://esco/123"}, "still_exploring": False, "open_to_adjacent": False},
        "value_status": "answered",
    }}
    vacancy_values = {element.element_id: {"value": {"occupation": {"esco_uri": "http://esco/123"}}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert items[0].alignment == Alignment.ALIGNED
    assert items[0].clarification_required is False


def test_esco_occupation_pick_no_overlap_is_misaligned_without_openness():
    element = _element(
        element_id="CAREER-PRIMARY-ROLE", category=Category.CAREER, comparator_key="esco_occupation_pick",
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {
        "value": {"occupation": {"esco_uri": "http://esco/AAA"}, "still_exploring": False, "open_to_adjacent": False},
        "value_status": "answered",
    }}
    vacancy_values = {element.element_id: {"value": {"occupation": {"esco_uri": "http://esco/BBB"}}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert items[0].alignment == Alignment.MISALIGNED


def test_esco_occupation_pick_still_exploring_softens_no_match():
    element = _element(
        element_id="CAREER-PRIMARY-ROLE", category=Category.CAREER, comparator_key="esco_occupation_pick",
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {
        "value": {"occupation": {"esco_uri": "http://esco/AAA"}, "still_exploring": True, "open_to_adjacent": False},
        "value_status": "answered",
    }}
    vacancy_values = {element.element_id: {"value": {"occupation": {"esco_uri": "http://esco/BBB"}}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert items[0].alignment == Alignment.WEAK_ALIGNMENT
    assert items[0].clarification_required is True


def test_nace_industry_overlap_matches_on_shared_code():
    element = _element(
        element_id="CAREER-INDUSTRIES", category=Category.CAREER, comparator_key="nace_industry_overlap",
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {
        "value": {"industries": [{"nace_code": "J", "raw_text": "Tech"}]}, "value_status": "answered",
    }}
    vacancy_values = {element.element_id: {"value": {"industries": [{"nace_code": "J"}]}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values=vacancy_values,
    )
    assert items[0].alignment == Alignment.ALIGNED


def test_family5_unscored_elements_are_excluded_from_matching_entirely():
    element = _element(
        element_id="CAREER-NARRATIVE", category=Category.CAREER, comparator_key="unscored",
        candidate_value_schema={"text": "string"}, vacancy_value_schema={},
    )
    dictionary = {element.element_id: element}
    talent_values = {element.element_id: {"value": {"text": "Some narrative"}, "value_status": "answered"}}
    items = build_item_results(
        talent_id="T-1", vacancy_id="VAC-1", dictionary=dictionary,
        talent_values=talent_values, vacancy_values={},
    )
    assert items == []
