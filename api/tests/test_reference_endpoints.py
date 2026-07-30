"""Real API test for GET /reference/institutions, /programs (Phase 4), and
/skills, /occupations, /isced-fields (Phase 5, vacancy-side required-skills/
occupations/education pickers) -- real bundled reference data, no mocks, no
external calls (offline datasets only)."""

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


def test_reference_search_requires_auth_and_returns_real_matches():
    talent_id = None
    try:
        with TestClient(app) as client:
            r = client.get("/reference/institutions?q=Delft")
            assert r.status_code == 401  # no token at all

            r = client.post("/candidates", json={
                "full_name": "Reference Search Test", "email": f"reference-search-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.get("/reference/institutions?q=Delft", headers=headers)
            assert r.status_code == 200, r.text
            names = [i["name"] for i in r.json()]
            assert any("Delft" in name for name in names)

            r = client.get("/reference/programs?q=Computer Science", headers=headers)
            assert r.status_code == 200, r.text
            names = [p["name"] for p in r.json()]
            assert any("Computer Science" in name for name in names)

            r = client.get("/reference/institutions?q=", headers=headers)
            assert r.status_code == 422  # min_length=1
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})


def test_skill_occupation_isced_search_open_to_companies_too():
    # Phase 5: companies need these three (vacancy-side required-skills/
    # occupations/education pickers), unlike institutions/programs above
    # which stay candidate-only in practice -- confirms the router's auth
    # was actually widened to allow "company", not just left candidate-only.
    company_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/companies", json={
                "legal_name": "Reference Search Test BV", "display_name": "Reference Search Test BV",
                "website_domain": f"reference-search-{uuid.uuid4()}.example.com",
                "contact_email": f"hr-{uuid.uuid4()}@example.com", "password": "test-password-123",
                "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            company_id = r.json()["company"]["company_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.get("/reference/skills?q=SQL", headers=headers)
            assert r.status_code == 200, r.text
            assert any(s["label"] == "SQL" for s in r.json())

            r = client.get("/reference/occupations?q=Data Scientist", headers=headers)
            assert r.status_code == 200, r.text
            assert any("scientist" in o["label"].lower() for o in r.json())

            r = client.get("/reference/isced-fields", headers=headers)
            assert r.status_code == 200, r.text
            fields = r.json()
            assert len(fields) == 29
            assert any(f["code"] == "061" for f in fields)
    finally:
        with engine.begin() as conn:
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})
