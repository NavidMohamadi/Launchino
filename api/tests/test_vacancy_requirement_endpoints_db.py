"""Real API + DB test for the vacancy-side EDU/CAP/TASK requirement shapes
(Phase 5 of Education/Capabilities/Task History -- required_education/
required_skills/required_occupations, see PROJECT_NOTES.md). Confirms
POST /vacancies/{id}/workshop persists these new shapes correctly -- no
mocks, no AI calls, real Neon DB."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.database import engine  # noqa: E402
from api.main import app  # noqa: E402


def test_vacancy_requirement_shapes_persist_correctly():
    company_id = None
    vacancy_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/companies", json={
                "legal_name": "Requirement Persist Test BV", "display_name": "Requirement Persist Test BV",
                "website_domain": f"requirement-persist-{uuid.uuid4()}.example.com",
                "contact_email": f"hr-{uuid.uuid4()}@example.com", "password": "test-password-123",
                "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            company_id = r.json()["company"]["company_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post("/vacancies", json={
                "category_weights": {
                    "PRACT": 12.5, "CAP": 12.5, "TASK": 12.5, "TEAM": 12.5,
                    "CAREER": 12.5, "MOT": 12.5, "ENV": 12.5, "EDU": 12.5,
                },
                "company_name": "Requirement Persist Test BV", "title": "Backend Engineer",
                "description_text": "Confirms vacancy-side EDU/CAP/TASK requirement shapes persist.",
            }, headers=headers)
            assert r.status_code == 201, r.text
            vacancy_id = r.json()["vacancy_id"]

            r = client.post(f"/vacancies/{vacancy_id}/workshop", json={"values": [
                {
                    "element_id": "EDU-HISTORY",
                    "value": {"required_education": [{"isced_code": "061", "level": "bachelor", "requirement": "required"}]},
                    "value_status": "answered", "source_type": "job_description",
                    "item_importance": 4, "requirement_type": "critical",
                },
                {
                    "element_id": "CAP-SKILLS",
                    "value": {"required_skills": [
                        {"esco_uri": "http://data.europa.eu/esco/skill/598de5b0-5b58-4ea7-8058-a4bc4d18c742",
                         "skill": "SQL", "level": "advanced", "requirement": "required"},
                    ]},
                    "value_status": "answered", "source_type": "job_description",
                    "item_importance": 4, "requirement_type": "critical",
                },
                {
                    "element_id": "TASK-EXPERIENCE",
                    "value": {"required_occupations": [
                        {"esco_uri": "http://data.europa.eu/esco/occupation/f2b15a0e-e65a-438a-affb-29b9d50b77d1",
                         "occupation": "software developer", "requirement": "preferred"},
                    ]},
                    "value_status": "answered", "source_type": "job_description",
                    "item_importance": 3, "requirement_type": "preferred",
                },
                {
                    "element_id": "TASK-YEARS", "value": {"required_level": 3},
                    "value_status": "answered", "source_type": "job_description",
                    "item_importance": 3, "requirement_type": "important",
                },
            ]}, headers=headers)
            assert r.status_code == 201, r.text
            assert r.json()["values_stored"] == 4

            with engine.connect() as conn:
                rows = {
                    row["element_id"]: json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
                    for row in conn.execute(
                        text("select element_id, value from vacancy_element_value where vacancy_id = :id"),
                        {"id": vacancy_id},
                    ).mappings().all()
                }

            assert rows["EDU-HISTORY"]["required_education"][0]["isced_code"] == "061"
            assert rows["EDU-HISTORY"]["required_education"][0]["level"] == "bachelor"
            assert rows["CAP-SKILLS"]["required_skills"][0]["skill"] == "SQL"
            assert rows["CAP-SKILLS"]["required_skills"][0]["level"] == "advanced"
            assert rows["TASK-EXPERIENCE"]["required_occupations"][0]["occupation"] == "software developer"
            assert rows["TASK-YEARS"]["required_level"] == 3
    finally:
        with engine.begin() as conn:
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})
