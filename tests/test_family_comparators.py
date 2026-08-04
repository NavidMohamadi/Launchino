"""Real unit tests for the v3 Fit Dictionary redesign's 5 scoring families
(see PROJECT_NOTES.md) -- pure-logic tests against src/ comparator functions,
no database involved."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from match_engine import alignment_bucket_for_percent, score_ordinal_requirement  # noqa: E402
from ordinal_comparators import score_ordinal_distance  # noqa: E402
from practical_comparators import (  # noqa: E402
    EDUCATION_LEVEL, SKILL_PROFICIENCY_LEVEL, score_capability_list_requirement, score_education_history,
    score_motivation_preferred_minimum,
)
from schemas import Alignment  # noqa: E402


# -- alignment_bucket_for_percent -------------------------------------------

def test_alignment_bucket_boundaries():
    assert alignment_bucket_for_percent(100) == Alignment.ALIGNED
    assert alignment_bucket_for_percent(84) == Alignment.ALIGNED
    assert alignment_bucket_for_percent(83.335) == Alignment.ALIGNED
    assert alignment_bucket_for_percent(83.3) == Alignment.POTENTIALLY_ALIGNED
    assert alignment_bucket_for_percent(50) == Alignment.POTENTIALLY_ALIGNED
    assert alignment_bucket_for_percent(49.9) == Alignment.WEAK_ALIGNMENT
    assert alignment_bucket_for_percent(16.665) == Alignment.WEAK_ALIGNMENT
    assert alignment_bucket_for_percent(16.6) == Alignment.MISALIGNED
    assert alignment_bucket_for_percent(0) == Alignment.MISALIGNED


# -- Family 1: score_ordinal_requirement (TEAM capability elements, TASK-YEARS) --

def test_family1_meets_or_exceeds_is_always_100_percent():
    alignment, reason, percent = score_ordinal_requirement(5, 3)
    assert percent == 100.0
    assert alignment == Alignment.ALIGNED
    alignment, reason, percent = score_ordinal_requirement(3, 3)
    assert percent == 100.0


def test_family1_shortfall_formula_exact_values():
    assert score_ordinal_requirement(4, 5)[2] == 75.0   # shortfall 1
    assert score_ordinal_requirement(3, 5)[2] == 50.0   # shortfall 2
    assert score_ordinal_requirement(2, 5)[2] == 25.0   # shortfall 3
    assert score_ordinal_requirement(1, 5)[2] == 0.0    # shortfall 4, floored


def test_family1_missing_value_is_unknown_no_score():
    alignment, reason, percent = score_ordinal_requirement(None, 5)
    assert alignment == Alignment.UNKNOWN
    assert percent is None


def test_family1_not_specified_required_level_is_unknown_not_a_crash():
    alignment, reason, percent = score_ordinal_requirement(3, "not_specified")
    assert alignment == Alignment.UNKNOWN
    assert percent is None


# -- Family 2: score_ordinal_distance (new ENV-*/RIASEC elements) --

def test_family2_symmetric_distance_exact_values():
    assert score_ordinal_distance(3, 3)[2] == 100.0
    assert score_ordinal_distance(3, 4)[2] == 80.0
    assert score_ordinal_distance(4, 3)[2] == 80.0  # symmetric -- overshoot penalized same as undershoot
    assert score_ordinal_distance(3, 5)[2] == 60.0
    assert score_ordinal_distance(1, 5)[2] == 20.0  # max distance floors at 20%, never 0


def test_family2_missing_value_is_unknown():
    alignment, reason, percent = score_ordinal_distance(None, 3)
    assert alignment == Alignment.UNKNOWN
    assert percent is None


def test_family2_not_specified_vacancy_value_is_unknown_not_a_crash():
    # Regression: "not_specified" is a real, documented vacancy value (not a
    # bug path) -- a real Phase 3 migration run against live data crashed
    # here with a TypeError before this was fixed.
    alignment, reason, percent = score_ordinal_distance(3, "not_specified")
    assert alignment == Alignment.UNKNOWN
    assert percent is None


# -- Family 3: score_motivation_preferred_minimum (MOT-CHALLENGE) --

def test_family3_above_minimum_gentle_penalty():
    # actual=4 clears minimum=2; preferred=5 -> |4-5|=1 -> 100-15=85
    alignment, reason, percent = score_motivation_preferred_minimum(
        {"preferred_level": 5, "minimum_acceptable_level": 2}, {"actual_level": 4},
    )
    assert percent == 85.0
    assert alignment == Alignment.ALIGNED


def test_family3_above_minimum_floors_at_40():
    # actual=1 clears minimum=1 (trivially); preferred=5 -> |1-5|=4 -> 100-60=40, matches floor exactly
    alignment, reason, percent = score_motivation_preferred_minimum(
        {"preferred_level": 5, "minimum_acceptable_level": 1}, {"actual_level": 1},
    )
    assert percent == 40.0


def test_family3_below_minimum_steeper_penalty():
    # actual=2 is below minimum=4 by 2 -> max(0, 40 - 20*2) = 0
    alignment, reason, percent = score_motivation_preferred_minimum(
        {"preferred_level": 3, "minimum_acceptable_level": 4}, {"actual_level": 2},
    )
    assert percent == 0.0
    assert alignment == Alignment.MISALIGNED


def test_family3_one_below_minimum():
    # actual=3 is below minimum=4 by 1 -> max(0, 40-20) = 20
    _, _, percent = score_motivation_preferred_minimum(
        {"preferred_level": 3, "minimum_acceptable_level": 4}, {"actual_level": 3},
    )
    assert percent == 20.0


def test_family3_missing_candidate_data_is_unknown():
    alignment, reason, percent = score_motivation_preferred_minimum({}, {"actual_level": 3})
    assert alignment == Alignment.UNKNOWN
    assert percent is None


def test_family3_vacancy_not_specified_is_unknown():
    alignment, reason, percent = score_motivation_preferred_minimum(
        {"preferred_level": 3, "minimum_acceptable_level": 2}, {"actual_level": "not_specified"},
    )
    assert alignment == Alignment.UNKNOWN
    assert percent is None


# -- Family 1 (list form): score_capability_list_requirement (CAP-SKILLS) --

def test_capability_list_meets_requirement():
    alignment, reason, percent = score_capability_list_requirement(
        [{"tag": "sql", "level": "advanced"}],
        [{"tag": "sql", "level": "intermediate"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert percent == 100.0
    assert alignment == Alignment.ALIGNED


def test_capability_list_shortfall_percent():
    # beginner=1, required expert=4 -> shortfall 3 -> max(0, 100-75)=25
    alignment, reason, percent = score_capability_list_requirement(
        [{"tag": "sql", "level": "beginner"}],
        [{"tag": "sql", "level": "expert"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert percent == 25.0


def test_capability_list_no_tag_overlap_is_misaligned_zero_percent():
    alignment, reason, percent = score_capability_list_requirement(
        [{"tag": "sql", "level": "expert"}],
        [{"tag": "rust", "level": "beginner"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert alignment == Alignment.MISALIGNED
    assert percent == 0.0


def test_capability_list_best_of_multiple_entries_wins():
    alignment, reason, percent = score_capability_list_requirement(
        [{"tag": "sql", "level": "beginner"}, {"tag": "sql", "level": "expert"}],
        [{"tag": "sql", "level": "advanced"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert percent == 100.0  # the expert entry clears advanced, even though beginner doesn't


def test_capability_list_no_required_entries_is_unknown():
    alignment, reason, percent = score_capability_list_requirement(
        [{"tag": "sql", "level": "expert"}], [], level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert alignment == Alignment.UNKNOWN
    assert percent is None


# -- Family 1 + conditional field requirement: score_education_history (EDU-HISTORY) --

def _edu_entry(level, isced_code=None, consider=True):
    return {"level": level, "field": {"isced_code": isced_code}, "consider": consider}


def test_education_open_ignores_field_scores_on_level_alone():
    alignment, reason, percent = score_education_history(
        [_edu_entry("master", isced_code="0388")],
        [{"level": "bachelor", "isced_code": "0611"}],
        field_requirement="open",
    )
    assert percent == 100.0  # master exceeds required bachelor; field (0388 vs 0611) ignored entirely


def test_education_required_caps_hard_on_field_mismatch():
    alignment, reason, percent = score_education_history(
        [_edu_entry("phd", isced_code="0388")],  # exceeds level requirement...
        [{"level": "bachelor", "isced_code": "0611"}],  # ...but wrong field, and field is required
        field_requirement="required",
    )
    assert percent == 0.0
    assert alignment == Alignment.MISALIGNED


def test_education_required_full_score_on_field_match():
    alignment, reason, percent = score_education_history(
        [_edu_entry("bachelor", isced_code="0611")],
        [{"level": "bachelor", "isced_code": "0611"}],
        field_requirement="required",
    )
    assert percent == 100.0


def test_education_preferred_reduces_but_does_not_zero_on_mismatch():
    alignment, reason, percent = score_education_history(
        [_edu_entry("bachelor", isced_code="0388")],
        [{"level": "bachelor", "isced_code": "0611"}],
        field_requirement="preferred",
    )
    assert 0.0 < percent < 100.0  # reduced, not capped to zero


def test_education_non_considered_entry_is_excluded():
    # Only entry is consider=False -> no eligible entries -> UNKNOWN, not a
    # (wrongly) scored match against an entry the candidate opted out of.
    alignment, reason, percent = score_education_history(
        [_edu_entry("phd", isced_code="0611", consider=False)],
        [{"level": "bachelor", "isced_code": "0611"}],
        field_requirement="required",
    )
    assert alignment == Alignment.UNKNOWN
    assert percent is None


def test_education_best_entry_among_multiple_wins():
    alignment, reason, percent = score_education_history(
        [_edu_entry("secondary", isced_code="0611"), _edu_entry("master", isced_code="0611")],
        [{"level": "bachelor", "isced_code": "0611"}],
        field_requirement="required",
    )
    assert percent == 100.0  # the master's-level entry clears it, even though secondary alone wouldn't


def test_education_no_required_level_is_unknown():
    alignment, reason, percent = score_education_history(
        [_edu_entry("bachelor", isced_code="0611")], [], field_requirement="open",
    )
    assert alignment == Alignment.UNKNOWN
    assert percent is None
