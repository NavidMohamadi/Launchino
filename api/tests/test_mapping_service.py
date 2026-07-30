"""Pure-logic tests for api/mapping_service.py.

Claude is never actually called: api.ai_client.call_claude_structured is
patched with a fake that runs the exact same validate_tool_output() path a
real call would, against a hand-written canned response -- same pattern as
api/tests/test_extraction_service.py. No network access, no
ANTHROPIC_API_KEY, no database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

import api.ai_client as ai_client  # noqa: E402
from api.mapping_service import (  # noqa: E402
    MAPPING_CONFIDENCE_THRESHOLD, map_occupation_to_esco, map_program_to_isced, map_skill_to_esco,
)

SKILL_OPTIONS = [
    {"uri": "u:sql", "label": "SQL"},
    {"uri": "u:mysql", "label": "MySQL"},
    {"uri": "u:python", "label": "Python (programming language)"},
    {"uri": "u:excel", "label": "Microsoft Excel"},
]


def _fake_call(canned: dict):
    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        return ai_client.validate_tool_output(canned, response_model)

    return fake_call_claude_structured


# --- map_skill_to_esco / map_occupation_to_esco: mocked Claude -----------

@patch("api.mapping_service.load_esco_skills")
def test_map_skill_high_confidence_does_not_require_confirmation(mock_load):
    mock_load.return_value = SKILL_OPTIONS
    canned = {"matched_code": "u:sql", "matched_label": "SQL", "confidence": 0.95, "reasoning": "Exact match."}
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_skill_to_esco("SQL")
    assert result.matched_code == "u:sql"
    assert result.confidence == 0.95
    assert result.requires_confirmation is False


@patch("api.mapping_service.load_esco_skills")
def test_map_skill_low_confidence_requires_confirmation(mock_load):
    mock_load.return_value = SKILL_OPTIONS
    canned = {
        "matched_code": "u:python", "matched_label": "Python (programming language)",
        "confidence": 0.4, "reasoning": "Ambiguous -- could mean the snake.",
    }
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_skill_to_esco("python")
    assert result.confidence < MAPPING_CONFIDENCE_THRESHOLD
    assert result.requires_confirmation is True


@patch("api.mapping_service.load_esco_skills")
def test_map_skill_no_match_requires_confirmation(mock_load):
    mock_load.return_value = SKILL_OPTIONS
    canned = {"matched_code": None, "matched_label": None, "confidence": 0.0, "reasoning": "Nothing in the shortlist denotes this skill."}
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_skill_to_esco("Underwater basket weaving")
    assert result.matched_code is None
    assert result.requires_confirmation is True


@patch("api.mapping_service.load_esco_skills")
def test_map_skill_empty_shortlist_never_calls_claude(mock_load):
    mock_load.return_value = []

    def unexpected_call(**kwargs):
        raise AssertionError("Claude should never be called when the shortlist is empty")

    with patch("api.ai_client.call_claude_structured", unexpected_call):
        result = map_skill_to_esco("SQL")
    assert result.matched_code is None
    assert result.requires_confirmation is True


@patch("api.mapping_service.load_esco_occupations")
def test_map_occupation_high_confidence(mock_load):
    mock_load.return_value = [{"uri": "u:data-scientist", "label": "data scientist"}]
    canned = {
        "matched_code": "u:data-scientist", "matched_label": "data scientist",
        "confidence": 0.9, "reasoning": "Direct match.",
    }
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_occupation_to_esco("Data Scientist")
    assert result.matched_code == "u:data-scientist"
    assert result.requires_confirmation is False


# --- map_program_to_isced: whole fixed list, no shortlist stage -----------

def test_map_program_to_isced_high_confidence():
    canned = {
        "matched_code": "061", "matched_label": "Information and Communication Technologies (ICTs)",
        "confidence": 0.92, "reasoning": "Clearly a computer science programme.",
    }
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_program_to_isced("BSc Computer Science")
    assert result.matched_code == "061"
    assert result.requires_confirmation is False


def test_map_program_to_isced_low_confidence_requires_confirmation():
    canned = {
        "matched_code": "003", "matched_label": "Personal skills and development",
        "confidence": 0.3, "reasoning": "Vague programme name, best-effort guess.",
    }
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        result = map_program_to_isced("General Studies")
    assert result.requires_confirmation is True


def test_map_program_schema_validation_failure_raises_clear_error():
    canned = {"matched_code": "061", "matched_label": None, "confidence": 1.5, "reasoning": "bad"}
    with patch("api.ai_client.call_claude_structured", _fake_call(canned)):
        with pytest.raises(ai_client.AIExtractionError):
            map_program_to_isced("BSc Computer Science")
