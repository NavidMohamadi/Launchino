"""Confirms the extraction endpoints never write to the database.

Runs against the real API + Neon (the project's configured dev DB) so the
row-count assertions mean something; Claude itself is still mocked via
unittest.mock.patch, so no ANTHROPIC_API_KEY or network call is involved.
Only the existing /survey and /workshop endpoints are expected to write to
talent_element_value / vacancy_element_value.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import api.ai_client as ai_client  # noqa: E402
from api.database import engine  # noqa: E402
from api.main import app  # noqa: E402


def _table_counts(conn, vacancy_id, talent_id):
    return {
        "talent": conn.execute(text("select count(*) from talent where talent_id = :id"), {"id": talent_id}).scalar_one(),
        "vacancy": conn.execute(text("select count(*) from vacancy where vacancy_id = :id"), {"id": vacancy_id}).scalar_one(),
        "talent_element_value": conn.execute(
            text("select count(*) from talent_element_value where talent_id = :id"), {"id": talent_id}
        ).scalar_one(),
        "vacancy_element_value": conn.execute(
            text("select count(*) from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id}
        ).scalar_one(),
    }


def test_extraction_endpoints_do_not_write_to_the_database():
    cv_response = {
        "extracted_elements": [
            {
                "value": {
                    "talent_id": "placeholder", "element_id": "PRACT-SPONSOR",
                    "value": {"requirement": "not_required"}, "value_status": "answered",
                    "source_type": "ai_extraction",
                },
                "source_quote": "I do not require visa sponsorship.",
                "extraction_confidence": 0.95,
            }
        ],
        "unanswered_element_ids": [],
        "review_flags": [],
    }
    vacancy_response = {
        "extracted_elements": [
            {
                "value": {
                    "vacancy_id": "placeholder", "element_id": "ENV-STRUCTURE",
                    "value": {"scale_id": "env_structure_1_5", "actual": 4}, "value_status": "answered",
                    "source_type": "ai_extraction",
                },
                "source_quote": "Goals are set at the start of each sprint.",
                "source_url": "shexon://vacancy-description-extraction",
                "extraction_confidence": 0.8, "source_snapshot_id": "shexon-manual-extraction",
            }
        ],
        "unanswered_element_ids": [],
        "review_flags": [],
    }

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        canned = cv_response if response_model.__name__ == "CandidateExtractionResult" else vacancy_response
        return ai_client.validate_tool_output(canned, response_model)

    talent_id = None
    vacancy_id = None
    company_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Extraction No-Write Test", "email": f"extraction-nowrite-{uuid.uuid4()}@example.com",
                "password": "test-password-123",
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            candidate_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post("/companies", json={
                "legal_name": "No Write BV", "display_name": "No Write BV",
                "website_domain": f"no-write-{uuid.uuid4()}.example.com",
                "contact_email": f"hr-{uuid.uuid4()}@example.com", "password": "test-password-123",
            })
            assert r.status_code == 201, r.text
            company_id = r.json()["company"]["company_id"]
            company_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post("/vacancies", json={
                "category_weights": {"PRACT": 100, "CAP": 0, "TASK": 0, "TEAM": 0, "CAREER": 0, "MOT": 0, "ENV": 0},
                "company_name": "No Write BV", "title": "Ops Analyst",
                "description_text": "Confirms extraction endpoints never write to the database.",
            }, headers=company_headers)
            assert r.status_code == 201, r.text
            vacancy_id = r.json()["vacancy_id"]

            with engine.connect() as conn:
                before = _table_counts(conn, vacancy_id, talent_id)

            with patch("api.ai_client.call_claude_structured", fake_call_claude_structured):
                r = client.post(
                    f"/candidates/{talent_id}/extract-cv", json={"cv_text": "5 years as a data analyst..."},
                    headers=candidate_headers,
                )
                assert r.status_code == 200, r.text
                assert r.json()["extracted_elements"][0]["value"]["element_id"] == "PRACT-SPONSOR"

                r = client.post(
                    f"/vacancies/{vacancy_id}/extract-description",
                    json={"description_text": "Goals are set at the start of each sprint..."},
                    headers=company_headers,
                )
                assert r.status_code == 200, r.text
                assert r.json()["extracted_elements"][0]["value"]["element_id"] == "ENV-STRUCTURE"

            with engine.connect() as conn:
                after = _table_counts(conn, vacancy_id, talent_id)

            assert after == before
            assert after["talent_element_value"] == 0
            assert after["vacancy_element_value"] == 0
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})


def test_confirmed_extraction_is_recorded_at_company_direct_trust_not_auto_extracted():
    """An AI-drafted, human-reviewed answer submitted through /workshop must be
    stamped verification_status=company_validated, the same trust level
    company-direct vacancy creation already uses -- not silently left at the
    DB's default 'auto_extracted' tier, which would make it indistinguishable
    from an unreviewed scrape."""
    vacancy_id = None
    company_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/companies", json={
                "legal_name": "Trust Level Check BV", "display_name": "Trust Level Check BV",
                "website_domain": f"trust-check-{uuid.uuid4()}.example.com",
                "contact_email": f"hr-{uuid.uuid4()}@example.com", "password": "test-password-123",
            })
            assert r.status_code == 201, r.text
            company_id = r.json()["company"]["company_id"]
            company_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post("/vacancies", json={
                "category_weights": {"PRACT": 100, "CAP": 0, "TASK": 0, "TEAM": 0, "CAREER": 0, "MOT": 0, "ENV": 0},
                "company_name": "Trust Level Check BV", "title": "Ops Analyst",
                "description_text": "Confirms /workshop submissions get company-direct trust.",
            }, headers=company_headers)
            assert r.status_code == 201, r.text
            vacancy_id = r.json()["vacancy_id"]

            # Simulates a human reviewing an extraction draft (source_type
            # ai_extraction) and resubmitting it as-is through /workshop --
            # the same field a naive frontend would carry over unedited.
            r = client.post(f"/vacancies/{vacancy_id}/workshop", json={"values": [
                {
                    "element_id": "PRACT-SPONSOR", "value": {"policy": "available"},
                    "value_status": "answered", "source_type": "ai_extraction",
                    "item_importance": 5, "requirement_type": "critical",
                },
            ]}, headers=company_headers)
            assert r.status_code == 201, r.text

            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "select source_type, verification_status from vacancy_element_value "
                        "where vacancy_id = :id and element_id = 'PRACT-SPONSOR'"
                    ),
                    {"id": vacancy_id},
                ).mappings().first()

            assert row["source_type"] == "ai_extraction"  # honest: this really was AI-drafted
            assert row["verification_status"] == "company_validated"  # but /workshop confirmed it
            assert row["verification_status"] != "auto_extracted"
    finally:
        with engine.begin() as conn:
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})
