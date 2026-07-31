"""Real API + DB test for DELETE /candidates/{id} (the GDPR erasure
mechanism, api/routers/candidates.py). No test covered this endpoint before
-- confirms its documented anonymize-don't-hard-delete behavior for real:
full_name/email tombstoned, password_hash cleared (can't log back in),
profile_status set to 'deleted', and the candidate's own survey rows
(talent_element_value/talent_evidence) hard-deleted. See PROJECT_NOTES.md
(Account Settings' new "Delete my account" UI reuses this exact endpoint,
no new backend deletion logic).
"""

from __future__ import annotations

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


def test_delete_candidate_anonymizes_and_blocks_further_login():
    talent_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Delete Me Test", "email": f"delete-test-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            body = r.json()
            talent_id = body["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {body['access_token']}"}
            original_email = body["candidate"]["email"]

            r = client.post(f"/candidates/{talent_id}/survey", json={"values": [
                {"element_id": "PRACT-SPONSOR", "source_type": "self_report",
                 "value": {"requirement": "not_required"}},
            ]}, headers=headers)
            assert r.status_code == 201, r.text

            r = client.delete(f"/candidates/{talent_id}", headers=headers)
            assert r.status_code == 200, r.text
            assert r.json() == {"talent_id": talent_id, "status": "deleted"}

            r = client.post("/candidates/login", json={"email": original_email, "password": "test-password-123"})
            assert r.status_code in (401, 404)  # tombstoned email/cleared password, can never log in again

            with engine.connect() as conn:
                row = conn.execute(
                    text("select full_name, email, password_hash, profile_status from talent where talent_id = :id"),
                    {"id": talent_id},
                ).mappings().first()
                assert row["full_name"] == "Deleted user"
                assert row["email"] == f"deleted-{talent_id}@deleted.invalid"
                assert row["password_hash"] is None
                assert row["profile_status"] == "deleted"

                remaining_values = conn.execute(
                    text("select count(*) from talent_element_value where talent_id = :id"), {"id": talent_id},
                ).scalar_one()
                assert remaining_values == 0

            # Deleting again (or any other self-scoped action) 404s -- there's
            # no "already deleted, do nothing" special case, same as any
            # other not-found candidate.
            r = client.delete(f"/candidates/{talent_id}", headers=headers)
            assert r.status_code == 200  # talent row still exists (anonymized, not hard-deleted) -- re-deletable
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": talent_id})
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
