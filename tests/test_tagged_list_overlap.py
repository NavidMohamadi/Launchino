from practical_comparators import EDUCATION_LEVEL, SKILL_PROFICIENCY_LEVEL, score_tagged_list_overlap
from schemas import Alignment


def test_no_vacancy_requirement_is_unknown():
    r = score_tagged_list_overlap([{"tag": "python", "level": "advanced"}], None, level_order=SKILL_PROFICIENCY_LEVEL, label="skills")
    assert r[0] == Alignment.UNKNOWN


def test_no_candidate_entries_is_unknown():
    r = score_tagged_list_overlap([], [{"tag": "python", "level": "intermediate"}], level_order=SKILL_PROFICIENCY_LEVEL, label="skills")
    assert r[0] == Alignment.UNKNOWN


def test_leveled_match_at_or_above_required_is_aligned():
    r = score_tagged_list_overlap(
        [{"tag": "python", "level": "advanced"}],
        [{"tag": "python", "level": "intermediate"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert r[0] == Alignment.ALIGNED


def test_leveled_one_below_required_is_weak():
    r = score_tagged_list_overlap(
        [{"tag": "python", "level": "beginner"}],
        [{"tag": "python", "level": "intermediate"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert r[0] == Alignment.WEAK_ALIGNMENT


def test_leveled_far_below_required_is_misaligned():
    r = score_tagged_list_overlap(
        [{"tag": "python", "level": "beginner"}],
        [{"tag": "python", "level": "expert"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert r[0] == Alignment.MISALIGNED


def test_no_tag_overlap_is_misaligned():
    r = score_tagged_list_overlap(
        [{"tag": "python", "level": "expert"}],
        [{"tag": "rust", "level": "beginner"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert r[0] == Alignment.MISALIGNED


def test_matches_any_one_of_multiple_required_tags():
    """'Matched by overlap' -- the candidate doesn't need every required tag,
    just at least one, mirroring score_set_compatibility's existing rule."""
    r = score_tagged_list_overlap(
        [{"tag": "sql", "level": None}],
        [{"tag": "python", "level": None}, {"tag": "sql", "level": None}],
        level_order=None, label="occupation experience",
    )
    assert r[0] == Alignment.ALIGNED


def test_unleveled_matches_on_tag_presence_only():
    """TASK's occupation-domain use case: level_order=None, pure overlap."""
    r = score_tagged_list_overlap(
        [{"tag": "2166.1", "level": None}],
        [{"tag": "2166.1", "level": None}],
        level_order=None, label="occupation experience",
    )
    assert r[0] == Alignment.ALIGNED


def test_unmapped_entry_still_compares_on_fallback_raw_text_tag():
    """An entry with no ESCO/ISCED mapping yet still gets literal-text
    comparability via its raw free-text fallback (see
    api/comparators_dispatch.py's _tags_from_entries), not silent exclusion."""
    r = score_tagged_list_overlap(
        [{"tag": "underwater basket weaving", "level": "advanced"}],
        [{"tag": "underwater basket weaving", "level": "beginner"}],
        level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
    )
    assert r[0] == Alignment.ALIGNED


def test_education_level_scale_orders_degrees_correctly():
    r = score_tagged_list_overlap(
        [{"tag": "0613", "level": "master"}],
        [{"tag": "0613", "level": "bachelor"}],
        level_order=EDUCATION_LEVEL, label="education",
    )
    assert r[0] == Alignment.ALIGNED
