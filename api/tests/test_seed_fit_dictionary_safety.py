"""Real-DB tests for seed_fit_dictionary's schema-change safety check
(api/database.py) -- added after a real question about the reseed
mechanism's blast radius, see PROJECT_NOTES.md. Uses a throwaway
element_id fully owned by each test (never a real production element like
TASK-EXPERIENCE), so a test can't leave the real Fit Dictionary in a
corrupted state the way manually exercising this against real data does.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from api.database import _is_schema_change_additive_only, engine, seed_fit_dictionary  # noqa: E402


def test_additive_only_detects_new_optional_key():
    assert _is_schema_change_additive_only({"a": "string"}, {"a": "string", "b": "string|null"}) is True


def test_additive_only_rejects_removed_key():
    assert _is_schema_change_additive_only({"a": "string"}, {"b": "string"}) is False


def test_additive_only_rejects_renamed_key():
    # Structurally indistinguishable from remove+add -- correctly caught by
    # "every old key must still be present", not a dedicated rename-detector.
    assert _is_schema_change_additive_only(
        {"jobs": [{"job_title": "string"}]}, {"jobs": [{"role_name": "string"}]},
    ) is False


def test_additive_only_rejects_type_change_on_existing_key():
    assert _is_schema_change_additive_only({"a": "string"}, {"a": "number"}) is False


def test_additive_only_accepts_new_key_inside_nested_array_template():
    assert _is_schema_change_additive_only(
        {"jobs": [{"job_title": "string"}]},
        {"jobs": [{"job_title": "string", "employer": "string|null"}]},
    ) is True


def test_additive_only_treats_empty_list_placeholder_as_compatible():
    # data/fit_dictionary_starter.json never ships an empty-array schema for
    # a real element, but test fixtures elsewhere in this suite do -- an
    # empty list has nothing concrete to compare against, so this must not
    # false-positive as incompatible.
    assert _is_schema_change_additive_only({"entries": []}, {"entries": [{"level": "string"}]}) is True


def _make_test_element(element_id: str, candidate_value_schema: dict) -> dict:
    return {
        "element_id": element_id, "category": "TASK", "label": "Test element",
        "definition": "d", "activation_policy": "always",
        "candidate_question": "q?", "vacancy_question": "q?",
        "candidate_value_schema": candidate_value_schema,
        "vacancy_value_schema": {"required_level": "integer"},
        "evidence_rule": "r", "comparator_key": "tagged_list_overlap_occupation",
        "sharing_status": "candidate_visible", "is_template": False, "version": "1.0.0", "active": True,
    }


def test_seed_blocks_incompatible_change_when_real_candidate_data_exists():
    element_id = f"TEST-SAFETY-{uuid.uuid4().hex[:8]}"
    talent_id = str(uuid.uuid4())
    try:
        original_schema = {"jobs": [{"job_title": "string"}]}
        seed_fit_dictionary(elements=[_make_test_element(element_id, original_schema)])

        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into talent (talent_id, full_name, email, password_hash, consent_at) "
                    "values (:id, 'Seed Safety Test', :email, 'x', now())"
                ),
                {"id": talent_id, "email": f"seed-safety-{talent_id}@example.com"},
            )
            conn.execute(
                text(
                    "insert into talent_element_value (talent_id, element_id, value, value_status, source_type, record_version) "
                    "values (:tid, :eid, cast(:val as jsonb), 'answered', 'self_report', 1)"
                ),
                {"tid": talent_id, "eid": element_id, "val": '{"jobs": [{"job_title": "Engineer"}]}'},
            )

        renamed_schema = {"jobs": [{"role_name": "string"}]}
        result = seed_fit_dictionary(elements=[_make_test_element(element_id, renamed_schema)])
        assert result == {"seeded_count": 0, "skipped": [{"element_id": element_id, "field": "candidate_value_schema"}]}

        with engine.connect() as conn:
            stored = conn.execute(
                text("select candidate_value_schema from fit_element where element_id = :eid"), {"eid": element_id},
            ).mappings().first()
        assert stored["candidate_value_schema"] == original_schema  # untouched, not silently overwritten
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from fit_element where element_id = :eid"), {"eid": element_id})


def test_seed_applies_incompatible_change_when_force_flag_given():
    element_id = f"TEST-SAFETY-{uuid.uuid4().hex[:8]}"
    talent_id = str(uuid.uuid4())
    try:
        seed_fit_dictionary(elements=[_make_test_element(element_id, {"jobs": [{"job_title": "string"}]})])
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into talent (talent_id, full_name, email, password_hash, consent_at) "
                    "values (:id, 'Seed Safety Test', :email, 'x', now())"
                ),
                {"id": talent_id, "email": f"seed-safety-{talent_id}@example.com"},
            )
            conn.execute(
                text(
                    "insert into talent_element_value (talent_id, element_id, value, value_status, source_type, record_version) "
                    "values (:tid, :eid, cast(:val as jsonb), 'answered', 'self_report', 1)"
                ),
                {"tid": talent_id, "eid": element_id, "val": '{"jobs": [{"job_title": "Engineer"}]}'},
            )

        renamed_schema = {"jobs": [{"role_name": "string"}]}
        result = seed_fit_dictionary(
            elements=[_make_test_element(element_id, renamed_schema)], force_element_ids=frozenset({element_id}),
        )
        assert result == {"seeded_count": 1, "skipped": []}

        with engine.connect() as conn:
            stored = conn.execute(
                text("select candidate_value_schema from fit_element where element_id = :eid"), {"eid": element_id},
            ).mappings().first()
        assert stored["candidate_value_schema"] == renamed_schema  # override applied
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from fit_element where element_id = :eid"), {"eid": element_id})


def test_seed_applies_incompatible_change_when_no_existing_data():
    # The whole point is protecting existing answered data -- an element
    # with none yet must not be blocked just because its schema changed.
    element_id = f"TEST-SAFETY-{uuid.uuid4().hex[:8]}"
    try:
        seed_fit_dictionary(elements=[_make_test_element(element_id, {"jobs": [{"job_title": "string"}]})])
        renamed_schema = {"jobs": [{"role_name": "string"}]}
        result = seed_fit_dictionary(elements=[_make_test_element(element_id, renamed_schema)])
        assert result == {"seeded_count": 1, "skipped": []}
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from fit_element where element_id = :eid"), {"eid": element_id})


def test_seed_applies_additive_change_automatically_even_with_existing_data():
    element_id = f"TEST-SAFETY-{uuid.uuid4().hex[:8]}"
    talent_id = str(uuid.uuid4())
    try:
        seed_fit_dictionary(elements=[_make_test_element(element_id, {"jobs": [{"job_title": "string"}]})])
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into talent (talent_id, full_name, email, password_hash, consent_at) "
                    "values (:id, 'Seed Safety Test', :email, 'x', now())"
                ),
                {"id": talent_id, "email": f"seed-safety-{talent_id}@example.com"},
            )
            conn.execute(
                text(
                    "insert into talent_element_value (talent_id, element_id, value, value_status, source_type, record_version) "
                    "values (:tid, :eid, cast(:val as jsonb), 'answered', 'self_report', 1)"
                ),
                {"tid": talent_id, "eid": element_id, "val": '{"jobs": [{"job_title": "Engineer"}]}'},
            )

        additive_schema = {"jobs": [{"job_title": "string", "employer": "string|null"}]}
        result = seed_fit_dictionary(elements=[_make_test_element(element_id, additive_schema)])
        assert result == {"seeded_count": 1, "skipped": []}  # applied automatically, no force needed
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
            conn.execute(text("delete from fit_element where element_id = :eid"), {"eid": element_id})
