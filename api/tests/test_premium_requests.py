"""Real-DB tests for the Premium request-and-manually-approve flow (Phase 2
of the candidate profile-dashboard task): POST /candidates/{id}/premium-request,
GET /admin/premium-requests, POST /admin/premium-requests/{id}/resolve.

Runs against the real API + Neon, no mocks. Admin auth: issues a token
directly via api.auth.create_access_token, same as test_admin_review.py.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.auth import ADMIN_TOKEN_EXPIRY, create_access_token  # noqa: E402
from api.main import app  # noqa: E402


def _admin_headers():
    token = create_access_token(subject="admin", role="admin", expires_delta=ADMIN_TOKEN_EXPIRY)
    return {"Authorization": f"Bearer {token}"}


def _make_candidate(client):
    r = client.post("/candidates", json={
        "full_name": "Premium Test Candidate", "email": f"premium-test-{uuid.uuid4()}@example.com",
        "password": "test-password-123", "data_processing_consent": True,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    return body["candidate"]["talent_id"], {"Authorization": f"Bearer {body['access_token']}"}


def test_submit_reject_duplicate_appear_in_admin_queue_approve_updates_subscription():
    admin_headers = _admin_headers()
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        # No pending request yet.
        r = client.get(f"/candidates/{talent_id}/premium-request", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() is None

        # Submit a real request.
        r = client.post(f"/candidates/{talent_id}/premium-request", headers=headers, json={"plan": "three_month"})
        assert r.status_code == 201, r.text
        request_id = r.json()["request_id"]
        assert r.json()["status"] == "pending"
        assert r.json()["plan"] == "three_month"

        # A second request while one is pending is rejected with a clear, specific error.
        r = client.post(f"/candidates/{talent_id}/premium-request", headers=headers, json={"plan": "one_month"})
        assert r.status_code == 409, r.text
        assert "pending" in r.json()["detail"].lower()

        # GET reflects the real pending state.
        r = client.get(f"/candidates/{talent_id}/premium-request", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["request_id"] == request_id

        # Appears in the real admin queue.
        r = client.get("/admin/premium-requests", headers=admin_headers)
        assert r.status_code == 200, r.text
        queued = [item for item in r.json() if item["request_id"] == request_id]
        assert len(queued) == 1, r.json()
        assert queued[0]["plan"] == "three_month"
        assert queued[0]["talent_id"] == talent_id

        # Approve -- must actually update the subscription, not just the request status.
        r = client.post(f"/admin/premium-requests/{request_id}/resolve", headers=admin_headers, json={"decision": "approve"})
        assert r.status_code == 200, r.text
        resolved = r.json()
        assert resolved["status"] == "approved"
        assert resolved["talent"]["job_discovery_subscription"] == "active"
        assert resolved["talent"]["subscription_source"] == "premium_request_approved"
        assert resolved["talent"]["subscription_expires_at"] is not None

        r = client.get(f"/candidates/{talent_id}", headers=headers)
        assert r.status_code == 200, r.text
        candidate = r.json()
        assert candidate["job_discovery_subscription"] == "active"
        assert candidate["subscription_source"] == "premium_request_approved"

        # No longer pending -- candidate can request again.
        r = client.get(f"/candidates/{talent_id}/premium-request", headers=headers)
        assert r.json() is None

        # Resolving an already-resolved request is rejected, not silently re-applied.
        r = client.post(f"/admin/premium-requests/{request_id}/resolve", headers=admin_headers, json={"decision": "approve"})
        assert r.status_code == 409, r.text


def test_deny_has_no_subscription_side_effect():
    admin_headers = _admin_headers()
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        r = client.post(f"/candidates/{talent_id}/premium-request", headers=headers, json={"plan": "one_month"})
        assert r.status_code == 201, r.text
        request_id = r.json()["request_id"]

        r = client.post(f"/admin/premium-requests/{request_id}/resolve", headers=admin_headers, json={"decision": "deny"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "denied"
        assert "talent" not in r.json()

        r = client.get(f"/candidates/{talent_id}", headers=headers)
        assert r.json()["job_discovery_subscription"] == "none"
