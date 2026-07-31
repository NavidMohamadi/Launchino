"""Pure-logic tests for api/extraction_service.py and api/ai_client.py.

Claude is never actually called: api.ai_client.call_claude_structured is
patched with a fake that runs the exact same validate_tool_output() path a
real call would (schema-forced tool call -> Pydantic validation), against a
hand-written canned response. No network access, no ANTHROPIC_API_KEY, no
database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from schemas import Category, FitElement, SharingStatus  # noqa: E402

import api.ai_client as ai_client  # noqa: E402
from api.ai_client import AIExtractionError  # noqa: E402
from api.extraction_service import (  # noqa: E402
    _scope_to_cv_extraction_categories, _scope_to_vacancy_extraction_categories, build_cv_extraction_prompt,
    build_vacancy_extraction_prompt, run_cv_extraction, run_vacancy_extraction,
)


def _element(**overrides) -> FitElement:
    # CAP is candidate-side profile content, always answerable independent
    # of any vacancy (Phase 1 of Education/Capabilities/Task History -- see
    # PROJECT_NOTES.md), not vacancy-gated as originally designed.
    base = dict(
        element_id="CAP-SQL", category=Category.CAP, label="SQL",
        definition="Writes and reads SQL queries.", activation_policy="always",
        candidate_question="q?", vacancy_question="q?",
        candidate_value_schema={"level": "integer 0..4"}, vacancy_value_schema={"required_level": "integer 0..4"},
        evidence_rule="rule", comparator_key="ordinal_requirement", sharing_status=SharingStatus.CANDIDATE_VISIBLE,
    )
    base.update(overrides)
    return FitElement.model_validate(base)


def _pract_element() -> FitElement:
    return _element(
        element_id="PRACT-SPONSOR", category=Category.PRACT, activation_policy="always",
        comparator_key="tri_state_requirement", candidate_value_schema={"requirement": "required|not_required|not_sure"},
        vacancy_value_schema={"policy": "available|conditional|unavailable|not_specified"},
    )


def _edu_element() -> FitElement:
    return _element(
        element_id="EDU-HISTORY", category=Category.EDU, activation_policy="always",
        comparator_key="tagged_list_overlap_education", candidate_value_schema={"entries": []},
        vacancy_value_schema={"required_education": []},
    )


def _task_element() -> FitElement:
    return _element(
        element_id="TASK-EXPERIENCE", category=Category.TASK, activation_policy="always",
        comparator_key="tagged_list_overlap_occupation", candidate_value_schema={"jobs": []},
        vacancy_value_schema={"required_occupations": []},
    )


def _career_element() -> FitElement:
    return _element(
        element_id="CAREER-GROWTH", category=Category.CAREER, activation_policy="always",
        comparator_key="ordinal_range", candidate_value_schema={"scale_id": "x"}, vacancy_value_schema={"scale_id": "x"},
    )


def _env_element() -> FitElement:
    return _element(
        element_id="ENV-STRUCTURE", category=Category.ENV, activation_policy="always",
        comparator_key="ordinal_range", candidate_value_schema={"scale_id": "env_structure_1_5"},
        vacancy_value_schema={"scale_id": "env_structure_1_5"},
    )


def test_model_for_task_mapping_is_correct_per_task():
    sonnet_tasks = {"cv_extraction", "vacancy_extraction", "match_explanation"}
    haiku_tasks = {
        "gap_questions", "clarification_questions", "source_classification",
        "duplicate_review_flagging", "sponsor_review_flagging",
        "skill_mapping", "occupation_mapping", "program_mapping",
    }
    assert set(ai_client.MODEL_FOR_TASK) == sonnet_tasks | haiku_tasks
    for task in sonnet_tasks:
        assert ai_client.MODEL_FOR_TASK[task] == "claude-sonnet-5"
    for task in haiku_tasks:
        assert ai_client.MODEL_FOR_TASK[task] == "claude-haiku-4-5-20251001"


def test_cv_extraction_success_parses_into_talent_element_value():
    canned = {
        "extracted_elements": [
            {
                "value": {
                    "talent_id": "T-1", "element_id": "CAP-SQL",
                    "value": {"level": 3, "evidence": "Built ETL pipelines in SQL for 3 years."},
                    "value_status": "answered", "source_type": "ai_extraction",
                },
                "source_quote": "Built ETL pipelines in SQL for 3 years.",
                "extraction_confidence": 0.9,
            }
        ],
        "unanswered_element_ids": ["CAP-PYTHON"],
        "review_flags": ["Confirm SQL proficiency level with the candidate directly."],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        result = run_cv_extraction(candidate_id="T-1", cv_text="... a CV ...", dictionary={"CAP-SQL": _element()})

    assert len(result.extracted_elements) == 1
    element = result.extracted_elements[0]
    assert element.value.element_id == "CAP-SQL"
    assert element.value.value["level"] == 3
    assert element.value.value_status.value == "answered"
    assert result.unanswered_element_ids == ["CAP-PYTHON"]


def test_cv_extraction_puts_real_but_unmatched_skills_in_unmapped_terms_not_invented_ids():
    # A real, valid skill (SQL) with no matching dictionary element must go in
    # unmapped_terms as a plain string, not become a fabricated element_id.
    canned = {
        "extracted_elements": [],
        "unmapped_terms": ["SQL", "Postgres", "Python (pandas)"],
        "unanswered_element_ids": [],
        "review_flags": ["Terms SQL, Postgres, and Python (pandas) require human review for possible new CAP elements."],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        result = run_cv_extraction(candidate_id="T-1", cv_text="... a CV mentioning SQL ...", dictionary={})

    assert result.extracted_elements == []
    assert result.unmapped_terms == ["SQL", "Postgres", "Python (pandas)"]


def test_cv_extraction_schema_validation_failure_raises_clear_error():
    # answered with an empty payload violates TalentElementValue.answered_requires_payload.
    canned = {
        "extracted_elements": [
            {
                "value": {
                    "talent_id": "T-1", "element_id": "CAP-SQL", "value": {},
                    "value_status": "answered", "source_type": "ai_extraction",
                },
                "source_quote": "unclear", "extraction_confidence": 0.4,
            }
        ],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        with pytest.raises(AIExtractionError):
            run_cv_extraction(candidate_id="T-1", cv_text="... a CV ...", dictionary={"CAP-SQL": _element()})


def test_vacancy_extraction_success_parses_into_vacancy_element_value():
    canned = {
        "extracted_elements": [
            {
                "value": {
                    "vacancy_id": "V-1", "element_id": "ENV-STRUCTURE",
                    "value": {"scale_id": "env_structure_1_5", "actual": 4},
                    "value_status": "answered", "source_type": "ai_extraction",
                },
                "source_quote": "Goals are set at the start of each sprint.",
                "source_url": "shexon://vacancy-description-extraction",
                "extraction_confidence": 0.8,
                "source_snapshot_id": "shexon-manual-extraction",
            }
        ],
        "unanswered_element_ids": [],
        "review_flags": ["Vague phrase: \"dynamic team\" needs clarification."],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        result = run_vacancy_extraction(
            vacancy_id="V-1", vacancy_text="... a vacancy description ...", dictionary={"ENV-STRUCTURE": _env_element()},
        )

    assert len(result.extracted_elements) == 1
    element = result.extracted_elements[0]
    assert element.value.element_id == "ENV-STRUCTURE"
    assert element.value.value["actual"] == 4
    assert "dynamic team" in result.review_flags[0]


def test_vacancy_extraction_schema_validation_failure_raises_clear_error():
    # UNKNOWN requires unknown_reason; this omits it while also carrying a
    # not_scored_reason it shouldn't have, violating ElementValueState.validate_state_reason.
    canned = {
        "extracted_elements": [
            {
                "value": {
                    "vacancy_id": "V-1", "element_id": "ENV-STRUCTURE", "value": {},
                    "value_status": "unknown", "not_scored_reason": "out_of_scope_by_design",
                    "source_type": "ai_extraction",
                },
                "source_quote": "n/a", "source_url": "shexon://vacancy-description-extraction",
                "extraction_confidence": 0.1, "source_snapshot_id": "shexon-manual-extraction",
            }
        ],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        with pytest.raises(AIExtractionError):
            run_vacancy_extraction(
                vacancy_id="V-1", vacancy_text="... a vacancy description ...", dictionary={"ENV-STRUCTURE": _env_element()},
            )


# --- Phase 3: CV extraction is structurally scoped to EDU+TASK only -------
# (revised 2026-07-31 -- was PRACT+EDU; PRACT removed, TASK added, see
# PROJECT_NOTES.md and CV_EXTRACTION_CATEGORIES's own comment.)

def test_cv_extraction_scoping_excludes_cap_pract_career_mot_env_even_if_active():
    # A hard code-level allowlist (CV_EXTRACTION_CATEGORIES), not a side
    # effect of which elements happen to be active=true -- so this must hold
    # even when given a dictionary spanning every category, all "active".
    # Checks the actual dictionary-scoping function directly rather than
    # grepping the full rendered prompt text: CV_ELEMENT_ID_RULE's own
    # worked example legitimately mentions "CAP-SQL" by name as an
    # anti-pattern, which a blunt substring check would misreport as a leak.
    full_dictionary = {
        "PRACT-SPONSOR": _pract_element(),
        "EDU-HISTORY": _edu_element(),
        "CAP-SQL": _element(),
        "TASK-EXPERIENCE": _task_element(),
        "CAREER-GROWTH": _career_element(),
        "ENV-STRUCTURE": _env_element(),
    }
    scoped = _scope_to_cv_extraction_categories(full_dictionary)
    assert set(scoped) == {"EDU-HISTORY", "TASK-EXPERIENCE"}


def test_cv_extraction_prompt_never_offers_out_of_scope_element_ids_as_valid():
    # The FIT_DICTIONARY_JSON blob embedded in the rendered prompt -- the
    # thing the model is actually told it may choose element_id from -- must
    # not contain any out-of-scope element_id, distinct from the rule text
    # merely discussing one as a named anti-pattern (see the test above).
    full_dictionary = {
        "PRACT-SPONSOR": _pract_element(), "EDU-HISTORY": _edu_element(),
        "CAP-SQL": _element(), "TASK-EXPERIENCE": _task_element(),
        "CAREER-GROWTH": _career_element(), "ENV-STRUCTURE": _env_element(),
    }
    _, user = build_cv_extraction_prompt(candidate_id="T-1", cv_text="a CV", dictionary=full_dictionary)
    dictionary_json_line = next(line for line in user.splitlines() if '"element_id": "EDU-HISTORY"' in line)
    assert "PRACT-SPONSOR" not in dictionary_json_line
    assert "CAP-SQL" not in dictionary_json_line
    assert "CAREER-GROWTH" not in dictionary_json_line
    assert "ENV-STRUCTURE" not in dictionary_json_line


# --- Phase 5: vacancy extraction excludes EDU/CAP/TASK --------------------

def test_vacancy_extraction_scoping_excludes_edu_cap_task_even_if_active():
    # A hard code-level exclusion (VACANCY_EXTRACTION_EXCLUDED_CATEGORIES),
    # not a side effect of which elements happen to be active=true --
    # PRACT/CAREER/ENV must survive scoping unchanged (vacancy extraction's
    # existing behavior for these is not being narrowed), while EDU/CAP/TASK
    # must always be excluded, mirroring CV_EXTRACTION_CATEGORIES's own test.
    full_dictionary = {
        "PRACT-SPONSOR": _pract_element(),
        "EDU-HISTORY": _edu_element(),
        "CAP-SQL": _element(),
        "TASK-EXPERIENCE": _task_element(),
        "CAREER-GROWTH": _career_element(),
        "ENV-STRUCTURE": _env_element(),
    }
    scoped = _scope_to_vacancy_extraction_categories(full_dictionary)
    assert set(scoped) == {"PRACT-SPONSOR", "CAREER-GROWTH", "ENV-STRUCTURE"}


def test_vacancy_extraction_prompt_never_offers_edu_cap_task_element_ids_as_valid():
    full_dictionary = {
        "PRACT-SPONSOR": _pract_element(), "EDU-HISTORY": _edu_element(),
        "CAP-SQL": _element(), "TASK-EXPERIENCE": _task_element(),
        "CAREER-GROWTH": _career_element(), "ENV-STRUCTURE": _env_element(),
    }
    _, user = build_vacancy_extraction_prompt(vacancy_id="V-1", vacancy_text="a vacancy", dictionary=full_dictionary)
    dictionary_json_line = next(line for line in user.splitlines() if '"element_id": "PRACT-SPONSOR"' in line)
    assert "EDU-HISTORY" not in dictionary_json_line
    assert "CAP-SQL" not in dictionary_json_line
    assert "TASK-EXPERIENCE" not in dictionary_json_line
    assert "CAREER-GROWTH" in dictionary_json_line  # confirms this isn't just an empty/broken dictionary


def test_cv_extraction_returns_basic_info_when_present():
    canned = {
        "extracted_elements": [],
        "basic_info": {"phone": "+31 6 1234 5678", "evidence_quote": "+31 6 1234 5678"},
        "unanswered_element_ids": [], "unmapped_terms": [], "review_flags": [],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        result = run_cv_extraction(candidate_id="T-1", cv_text="... a CV ...", dictionary={})

    assert result.basic_info is not None
    assert result.basic_info.phone == "+31 6 1234 5678"


def test_cv_extraction_basic_info_defaults_to_none_when_absent():
    canned = {"extracted_elements": [], "unanswered_element_ids": [], "unmapped_terms": [], "review_flags": []}

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
        result = run_cv_extraction(candidate_id="T-1", cv_text="... a CV with no contact info ...", dictionary={})

    assert result.basic_info is None
