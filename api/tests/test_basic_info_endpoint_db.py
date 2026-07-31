"""Real API + DB test for PATCH /candidates/{id}/basic-info (Phase 3 of
Education/Capabilities/Task History -- phone/contact_preference, plain
talent columns, not a Fit Dictionary category).
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


def test_basic_info_partial_update_and_defaults():
    talent_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Basic Info Test", "email": f"basic-info-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            # New account: contact_preference has no default and starts
            # genuinely unset (None), same as phone -- a candidate who has
            # never visited Account Settings has never made a real choice
            # (see PROJECT_NOTES.md).
            body = r.json()["candidate"]
            assert body["contact_preference"] is None
            assert body["phone"] is None

            r = client.patch(f"/candidates/{talent_id}/basic-info", json={"phone": "+31 6 1111 2222"}, headers=headers)
            assert r.status_code == 200, r.text
            assert r.json()["phone"] == "+31 6 1111 2222"
            assert r.json()["contact_preference"] is None  # untouched -- still no real choice made

            r = client.patch(
                f"/candidates/{talent_id}/basic-info", json={"contact_preference": "either"}, headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["phone"] == "+31 6 1111 2222"  # still there, untouched by this second call
            assert r.json()["contact_preference"] == "either"

            r = client.get(f"/candidates/{talent_id}", headers=headers)
            assert r.status_code == 200, r.text
            assert r.json()["phone"] == "+31 6 1111 2222"
            assert r.json()["contact_preference"] == "either"

            r = client.patch(
                f"/candidates/{talent_id}/basic-info", json={"contact_preference": "not_a_real_value"}, headers=headers,
            )
            assert r.status_code == 422

            r = client.patch(f"/candidates/{uuid.uuid4()}/basic-info", json={"phone": "x"}, headers=headers)
            assert r.status_code == 403  # not this candidate's own talent_id
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})


def test_phone_required_only_when_contact_preference_is_phone():
    talent_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/candidates", json={
                "full_name": "Conditional Phone Test", "email": f"conditional-phone-{uuid.uuid4()}@example.com",
                "password": "test-password-123", "data_processing_consent": True,
            })
            assert r.status_code == 201, r.text
            talent_id = r.json()["candidate"]["talent_id"]
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            # Switching to "phone" with no phone on file at all (contact_preference starts unset, phone null) -- rejected.
            r = client.patch(f"/candidates/{talent_id}/basic-info", json={"contact_preference": "phone"}, headers=headers)
            assert r.status_code == 422, r.text

            # Non-phone preferences never require a phone number.
            for pref in ["email", "either"]:
                r = client.patch(f"/candidates/{talent_id}/basic-info", json={"contact_preference": pref}, headers=headers)
                assert r.status_code == 200, r.text

            # Setting both together in one request -- allowed.
            r = client.patch(
                f"/candidates/{talent_id}/basic-info",
                json={"phone": "+31 6 1111 2222", "contact_preference": "phone"},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["contact_preference"] == "phone"

            # Now phone is already on file -- switching to "phone" via contact_preference
            # alone (phone omitted from this request) succeeds, checked against the
            # existing DB value, not just this request's own fields.
            r = client.patch(f"/candidates/{talent_id}/basic-info", json={"contact_preference": "email"}, headers=headers)
            assert r.status_code == 200, r.text
            r = client.patch(f"/candidates/{talent_id}/basic-info", json={"contact_preference": "phone"}, headers=headers)
            assert r.status_code == 200, r.text
            assert r.json()["phone"] == "+31 6 1111 2222"

            # "in_app_only" no longer exists as a valid preference.
            r = client.patch(f"/candidates/{talent_id}/basic-info", json={"contact_preference": "in_app_only"}, headers=headers)
            assert r.status_code == 422, r.text
    finally:
        with engine.begin() as conn:
            if talent_id:
                conn.execute(text("delete from talent where talent_id = :id"), {"id": talent_id})
