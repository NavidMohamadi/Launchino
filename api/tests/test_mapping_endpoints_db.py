"""Real API + DB test for the /candidates/{id}/map-skill|map-occupation|map-program
endpoints (api/mapping_service.py, Phase 2 of Education/Capabilities/Task
History). Claude is mocked via unittest.mock.patch (same pattern as
api/tests/test_extraction_endpoints_db.py); the running Neon dev DB is real,
so the "never writes to talent_element_value" assertion means something.
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


def test_map_endpoints_return_confidence_and_never_write_to_the_database():
    canned = {"matched_code": "u:sql", "matched_label": "SQL", "confidence": 0.95, "reasoning": "Exact match."}
    canned_low = {"matched_code": "u:vague", "matched_label": "General Studies", "confidence": 0.2, "reasoning": "Vague term."}

    def fake_call_claude_structured(*, model, system, user, response_model, **kwargs):
        is_program_prompt = "isced" in user.lower()
        return ai_client.validate_tool_output(canned_low if is_program_prompt else canned, response_model)

    talent_id = None
    other_talent_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Mapping Endpoint Test", "email": f"mapping-endpoint-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            with engine.connect() as conn:
                before = conn.execute(
                    text("select count(*) from talent_element_value where talent_id = :id"), {"id": talent_id}
                ).scalar_one()

            with patch("api.ai_client.call_claude_structured", fake_call_claude_structured), \
                 patch("api.mapping_service.load_esco_skills", return_value=[{"uri": "u:sql", "label": "SQL"}]), \
                 patch("api.mapping_service.load_esco_occupations", return_value=[{"uri": "u:x", "label": "x"}]):

                r = client.post(f"/candidates/{talent_id}/map-skill", json={"term": "SQL"}, headers=headers)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["matched_code"] == "u:sql"
                assert body["requires_confirmation"] is False

                r = client.post(f"/candidates/{talent_id}/map-program", json={"term": "something vague"}, headers=headers)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["requires_confirmation"] is True  # confidence 0.2 < threshold

            with engine.connect() as conn:
                after = conn.execute(
                    text("select count(*) from talent_element_value where talent_id = :id"), {"id": talent_id}
                ).scalar_one()

            assert after == before == 0

            # Wrong candidate's token must not be able to call another candidate's mapping endpoint.
            r2 = client.post("/candidates", json={
                "full_name": "Other Candidate", "email": f"other-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            other_talent_id = r2.json()["candidate"]["talent_id"]
            other_headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}
            r = client.post(f"/candidates/{talent_id}/map-skill", json={"term": "SQL"}, headers=other_headers)
            assert r.status_code == 403
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
            if other_talent_id:
                conn.execute(text("delete from talent where talent_id = :id"), {"id": other_talent_id})
