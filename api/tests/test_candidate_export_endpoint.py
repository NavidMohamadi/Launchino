"""Real API + DB test for GET /candidates/{id}/export (the GDPR data-export
mechanism, api/routers/candidates.py). Confirms it covers the fields added
after the endpoint was originally built: phone/contact_preference/
subscription_updated_at (Basic Info, Phase 3) and EDU/CAP/TASK survey
answers (Phase 4) -- previously the endpoint's talent SELECT still only
named the columns that existed when it was first written. See
PROJECT_NOTES.md.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.database import engine  # noqa: E402
from api.main import app  # noqa: E402
from sqlalchemy import text  # noqa: E402


def test_export_includes_basic_info_and_edu_cap_task_answers():
    talent_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Export Test Candidate", "email": f"export-test-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.patch(f"/candidates/{talent_id}/basic-info", json={
                "phone": "+31 6 1111 2222", "contact_preference": "phone",
            }, headers=headers)
            assert r.status_code == 200, r.text

            r = client.post(f"/candidates/{talent_id}/survey", json={"values": [
                {"element_id": "EDU-HISTORY", "source_type": "self_report", "value": {"entries": [{
                    "level": "bachelor", "institution": {"ror_id": None, "name": "Test University"},
                    "program": "Computer Science", "field": {"isced_code": None, "confidence": None},
                    "start_date": "2015-01-01", "end_date": "2019-01-01", "status": "completed",
                }]}},
                {"element_id": "CAP-SKILLS", "source_type": "self_report", "value": {"skills": [
                    {"skill": "SQL", "level": "advanced", "esco_uri": None, "confidence": None},
                ]}},
                {"element_id": "TASK-EXPERIENCE", "source_type": "self_report", "value": {"jobs": [
                    {"job_title": "Software Engineer", "esco_uri": None, "confidence": None,
                     "start_date": "2019-06-01", "end_date": None, "current": True},
                ]}},
            ]}, headers=headers)
            assert r.status_code == 201, r.text

            r = client.get(f"/candidates/{talent_id}/export", headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()

        profile = body["profile"]
        assert profile["phone"] == "+31 6 1111 2222"
        assert profile["contact_preference"] == "phone"
        assert "subscription_updated_at" in profile
        assert "password_hash" not in profile  # security credential, not exported personal data

        answers_by_element = {a["element_id"]: a for a in body["survey_answers"]}
        assert answers_by_element["EDU-HISTORY"]["value"]["entries"][0]["program"] == "Computer Science"
        assert answers_by_element["CAP-SKILLS"]["value"]["skills"][0]["skill"] == "SQL"
        assert answers_by_element["TASK-EXPERIENCE"]["value"]["jobs"][0]["job_title"] == "Software Engineer"
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
