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
from api.extraction_service import run_cv_extraction, run_vacancy_extraction  # noqa: E402


def _element(**overrides) -> FitElement:
    base = dict(
        element_id="CAP-SQL", category=Category.CAP, label="SQL",
        definition="Writes and reads SQL queries.", activation_policy="vacancy_activated",
        candidate_question="q?", vacancy_question="q?",
        candidate_value_schema={"level": "integer 0..4"}, vacancy_value_schema={"required_level": "integer 0..4"},
        evidence_rule="rule", comparator_key="ordinal_requirement", sharing_status=SharingStatus.CANDIDATE_VISIBLE,
    )
    base.update(overrides)
    return FitElement.model_validate(base)


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
