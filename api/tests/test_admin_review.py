"""Real-DB tests for Phase 2's admin review-queue endpoints
(api/routers/admin_review.py). Runs against the real API + Neon, like
test_extraction_endpoints_db.py -- no Claude calls involved here at all, so
nothing is mocked.

Admin auth: issues a token directly via api.auth.create_access_token (the
same function POST /admin/login itself uses) rather than logging in over
HTTP, since the real admin password is a bcrypt hash in .env with no
plaintext copy anywhere in the codebase to test against.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.auth import ADMIN_TOKEN_EXPIRY, create_access_token  # noqa: E402
from api.database import engine  # noqa: E402
from api.main import app  # noqa: E402


def _admin_headers():
    token = create_access_token(subject="admin", role="admin", expires_delta=ADMIN_TOKEN_EXPIRY)
    return {"Authorization": f"Bearer {token}"}


def _make_vacancy(client, company_headers, *, title="Test Role"):
    r = client.post(
        "/vacancies",
        json={
            "category_weights": {"PRACT": 100, "CAP": 0, "TASK": 0, "TEAM": 0, "CAREER": 0, "MOT": 0, "ENV": 0},
            "company_name": "Admin Review Test Co", "title": title,
            "description_text": "Confirms admin review-queue endpoints work end to end.",
        },
        headers=company_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["vacancy_id"]


def _make_company(client):
    r = client.post(
        "/companies",
        json={
            "legal_name": "Admin Review Test Co", "display_name": "Admin Review Test Co",
            "website_domain": f"admin-review-{uuid.uuid4()}.example.com",
            "contact_email": f"hr-{uuid.uuid4()}@example.com", "password": "test-password-123",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return body["company"]["company_id"], {"Authorization": f"Bearer {body['access_token']}"}


def test_dedup_review_list_resolve_and_disappear():
    admin_headers = _admin_headers()
    company_id = None
    vacancy_id = None
    snapshot_id = f"snap-test-{uuid.uuid4().hex[:16]}"
    review_id = None
    try:
        with TestClient(app) as client:
            company_id, company_headers = _make_company(client)
            vacancy_id = _make_vacancy(client, company_headers)

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into source_snapshot (
                            snapshot_id, source_record_id, source_id, source_url, external_job_id,
                            retrieved_at, content_hash, raw_payload, trust_level
                        ) values (
                            :snapshot_id, 'test-source-record', 'greenhouse_public_api', 'https://example.com/job/1',
                            'ext-1', :retrieved_at, :content_hash, cast(:raw_payload as jsonb), 4
                        )
                        """
                    ),
                    {
                        "snapshot_id": snapshot_id, "retrieved_at": datetime.now(timezone.utc),
                        "content_hash": uuid.uuid4().hex, "raw_payload": "{}",
                    },
                )
                review_id = conn.execute(
                    text(
                        """
                        insert into vacancy_dedup_review (
                            review_id, incoming_snapshot_id, candidate_vacancy_id, decision_reason,
                            confidence, status
                        ) values (
                            gen_random_uuid(), :snapshot_id, :vacancy_id, 'test fixture: high title similarity',
                            0.87, 'pending'
                        ) returning review_id
                        """
                    ),
                    {"snapshot_id": snapshot_id, "vacancy_id": vacancy_id},
                ).scalar_one()

            r = client.get("/admin/dedup-review", headers=admin_headers)
            assert r.status_code == 200, r.text
            pending_ids = [item["review_id"] for item in r.json()]
            assert str(review_id) in pending_ids

            found = next(item for item in r.json() if item["review_id"] == str(review_id))
            assert found["confidence"] == 0.87
            assert found["existing_vacancy"]["title"] == "Test Role"
            assert found["incoming_source"]["source_id"] == "greenhouse_public_api"

            r = client.post(
                f"/admin/dedup-review/{review_id}/resolve", json={"decision": "duplicate", "note": "test resolution"},
                headers=admin_headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "merge"

            r = client.get("/admin/dedup-review", headers=admin_headers)
            assert r.status_code == 200, r.text
            assert str(review_id) not in [item["review_id"] for item in r.json()]

            with engine.connect() as conn:
                row = conn.execute(
                    text("select status, reviewed_by, reviewed_at, review_note from vacancy_dedup_review where review_id = :id"),
                    {"id": str(review_id)},
                ).mappings().first()
                assert row["status"] == "merge"
                assert row["reviewed_by"]
                assert row["reviewed_at"] is not None
                assert row["review_note"] == "test resolution"

            # A different vacancy's ownership must not matter for admin -- no
            # separate assertion needed here, api/auth.py's require_role("admin")
            # is already covered elsewhere; this test is about the queue itself.

            # Resolving an already-resolved item must fail loudly, not silently re-resolve.
            r = client.post(
                f"/admin/dedup-review/{review_id}/resolve", json={"decision": "duplicate"}, headers=admin_headers,
            )
            assert r.status_code == 409, r.text
    finally:
        with engine.begin() as conn:
            if review_id:
                conn.execute(text("delete from vacancy_dedup_review where review_id = :id"), {"id": str(review_id)})
            conn.execute(text("delete from vacancy_source_link where snapshot_id = :id"), {"id": snapshot_id})
            conn.execute(text("delete from source_snapshot where snapshot_id = :id"), {"id": snapshot_id})
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})


def test_dedup_review_not_duplicate_marks_create_separate():
    admin_headers = _admin_headers()
    company_id = None
    vacancy_id = None
    snapshot_id = f"snap-test-{uuid.uuid4().hex[:16]}"
    review_id = None
    try:
        with TestClient(app) as client:
            company_id, company_headers = _make_company(client)
            vacancy_id = _make_vacancy(client, company_headers, title="Another Role")

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into source_snapshot (
                            snapshot_id, source_record_id, source_id, source_url, external_job_id,
                            retrieved_at, content_hash, raw_payload, trust_level
                        ) values (
                            :snapshot_id, 'test-source-record-2', 'lever_public_api', 'https://example.com/job/2',
                            'ext-2', :retrieved_at, :content_hash, cast(:raw_payload as jsonb), 4
                        )
                        """
                    ),
                    {
                        "snapshot_id": snapshot_id, "retrieved_at": datetime.now(timezone.utc),
                        "content_hash": uuid.uuid4().hex, "raw_payload": "{}",
                    },
                )
                review_id = conn.execute(
                    text(
                        """
                        insert into vacancy_dedup_review (
                            review_id, incoming_snapshot_id, candidate_vacancy_id, decision_reason, status
                        ) values (gen_random_uuid(), :snapshot_id, :vacancy_id, 'test fixture', 'pending')
                        returning review_id
                        """
                    ),
                    {"snapshot_id": snapshot_id, "vacancy_id": vacancy_id},
                ).scalar_one()

            r = client.post(
                f"/admin/dedup-review/{review_id}/resolve", json={"decision": "not_duplicate"}, headers=admin_headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "create_separate"

            r = client.get("/admin/dedup-review", headers=admin_headers)
            assert str(review_id) not in [item["review_id"] for item in r.json()]
    finally:
        with engine.begin() as conn:
            if review_id:
                conn.execute(text("delete from vacancy_dedup_review where review_id = :id"), {"id": str(review_id)})
            conn.execute(text("delete from source_snapshot where snapshot_id = :id"), {"id": snapshot_id})
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})


def test_sponsor_review_list_confirm_and_disappear():
    admin_headers = _admin_headers()
    company_id = None
    vacancy_id = None
    try:
        with TestClient(app) as client:
            company_id, company_headers = _make_company(client)
            vacancy_id = _make_vacancy(client, company_headers, title="Sponsor Test Role")

            fuzzy_signal = {
                "recognised_sponsor": None, "possible_match": True, "human_review_required": True,
                "match_method": "fuzzy_name", "registry_name": "IND public register Work",
                "matched_organisation_name": "Admin Review Test Co B.V.", "match_confidence": 0.81,
                "note": "Fuzzy name match -- legal entity is not yet verified.",
            }
            with engine.begin() as conn:
                conn.execute(
                    text("update vacancy set sponsorship_signal = cast(:signal as jsonb) where vacancy_id = :id"),
                    {"signal": __import__("json").dumps(fuzzy_signal), "id": vacancy_id},
                )

            r = client.get("/admin/sponsor-review", headers=admin_headers)
            assert r.status_code == 200, r.text
            pending_ids = [item["vacancy_id"] for item in r.json()]
            assert vacancy_id in pending_ids
            found = next(item for item in r.json() if item["vacancy_id"] == vacancy_id)
            assert found["sponsorship_signal"]["match_method"] == "fuzzy_name"

            r = client.post(
                f"/admin/sponsor-review/{vacancy_id}/resolve", json={"decision": "confirm"}, headers=admin_headers,
            )
            assert r.status_code == 200, r.text
            resolved = r.json()
            assert resolved["recognised_sponsor"] is True
            assert resolved["possible_match"] is False
            assert resolved["human_review_required"] is False
            assert resolved["match_method"] == "exact_legal_name"

            r = client.get("/admin/sponsor-review", headers=admin_headers)
            assert vacancy_id not in [item["vacancy_id"] for item in r.json()]
    finally:
        with engine.begin() as conn:
            if vacancy_id:
                conn.execute(text("delete from vacancy_element_value where vacancy_id = :id"), {"id": vacancy_id})
                conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": vacancy_id})
            if company_id:
                conn.execute(text("delete from company where company_id = :id"), {"id": company_id})


def test_extraction_review_lists_ai_extraction_submissions():
    admin_headers = _admin_headers()
    candidate_id = None
    try:
        with TestClient(app) as client:
            r = client.post(
                "/candidates",
                json={
                    "full_name": "Extraction Review Test", "email": f"extraction-review-{uuid.uuid4()}@example.com",
                    "password": "test-password-123",
                },
            )
            assert r.status_code == 201, r.text
            candidate_id = r.json()["candidate"]["talent_id"]
            candidate_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post(
                f"/candidates/{candidate_id}/survey",
                json={"values": [{
                    "element_id": "PRACT-SPONSOR", "value": {"requirement": "not_required"},
                    "value_status": "answered", "source_type": "ai_extraction",
                }]},
                headers=candidate_headers,
            )
            assert r.status_code == 201, r.text

            r = client.get("/admin/extraction-review", headers=admin_headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert "note" in body and "never persist" in body["note"]
            matches = [s for s in body["candidate_submissions"] if s["talent_id"] == candidate_id]
            assert len(matches) == 1
            assert matches[0]["element_id"] == "PRACT-SPONSOR"
            assert matches[0]["value"] == {"requirement": "not_required"}
    finally:
        with engine.begin() as conn:
            if candidate_id:
                conn.execute(text("delete from talent_element_value where talent_id = :id"), {"id": candidate_id})
                conn.execute(text("delete from talent where talent_id = :id"), {"id": candidate_id})


def test_non_admin_cannot_reach_review_endpoints():
    with TestClient(app) as client:
        r = client.get("/admin/dedup-review")
        assert r.status_code == 401
        r = client.get("/admin/sponsor-review")
        assert r.status_code == 401
        r = client.get("/admin/extraction-review")
        assert r.status_code == 401
