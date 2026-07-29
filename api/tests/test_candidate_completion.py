"""Real-DB tests for GET /candidates/{id}/completion (Phase 1 of the
candidate profile-dashboard task). Runs against the real API + Neon, no
mocks -- confirms the per-category breakdown tracks real
talent_element_value rows, not a placeholder.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


def _make_candidate(client):
    r = client.post("/candidates", json={
        "full_name": "Completion Test Candidate", "email": f"completion-test-{uuid.uuid4()}@example.com",
        "password": "test-password-123", "data_processing_consent": True,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    return body["candidate"]["talent_id"], {"Authorization": f"Bearer {body['access_token']}"}


def test_completion_starts_at_zero_and_tracks_real_answers():
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["talent_id"] == talent_id
        assert body["overall_percent_complete"] == 0.0
        by_category = {c["category"]: c for c in body["categories"]}
        assert set(by_category) == {"PRACT", "TEAM", "CAREER", "MOT", "ENV"}
        pract = by_category["PRACT"]
        assert pract["label"] == "Practical fit"
        assert pract["status"] == "not_started"
        assert pract["percent_complete"] == 0.0
        assert pract["active_item_count"] == 6  # 6 real ALWAYS-activated PRACT elements

        # Answer 3 of PRACT's 6 real elements -- real values, real schema keys.
        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {
                    "element_id": "PRACT-SPONSOR", "value": {"requirement": "not_required"},
                    "value_status": "answered", "source_type": "self_report",
                },
                {
                    "element_id": "PRACT-START", "value": {"earliest_start": "2026-09-01"},
                    "value_status": "answered", "source_type": "self_report",
                },
                {
                    "element_id": "PRACT-WORKMODE", "value": {"acceptable": ["hybrid", "remote"]},
                    "value_status": "answered", "source_type": "self_report",
                },
            ],
        })
        assert r.status_code == 201, r.text

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        by_category = {c["category"]: c for c in body["categories"]}
        pract = by_category["PRACT"]
        assert pract["status"] == "in_progress"
        assert pract["answered_item_count"] == 3
        assert pract["active_item_count"] == 6
        assert pract["percent_complete"] == 50.0
        # Untouched categories are still genuinely not_started, not a stale default.
        assert by_category["ENV"]["status"] == "not_started"

        # Answer the remaining 3 PRACT elements -> category flips to complete.
        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {
                    "element_id": "PRACT-COUNTRY",
                    "value": {"current_country": "NL", "presence_relative_to_vacancy": "in_country"},
                    "value_status": "answered", "source_type": "self_report",
                },
                {
                    "element_id": "PRACT-LANG", "value": {"languages": {"English": "fluent"}},
                    "value_status": "answered", "source_type": "self_report",
                },
                {
                    "element_id": "PRACT-CONTRACT", "value": {"acceptable": ["full_time"]},
                    "value_status": "answered", "source_type": "self_report",
                },
            ],
        })
        assert r.status_code == 201, r.text

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        body = r.json()
        by_category = {c["category"]: c for c in body["categories"]}
        assert by_category["PRACT"]["status"] == "complete"
        assert by_category["PRACT"]["percent_complete"] == 100.0


def test_completion_requires_self_or_admin():
    with TestClient(app) as client:
        talent_id, _headers = _make_candidate(client)
        other_talent_id, other_headers = _make_candidate(client)

        r = client.get(f"/candidates/{talent_id}/completion", headers=other_headers)
        assert r.status_code == 403, r.text

        r = client.get(f"/candidates/{talent_id}/completion")
        assert r.status_code == 401, r.text


def test_survey_values_returns_latest_saved_answers_for_prefill():
    """Real-DB test for GET /candidates/{id}/survey-values -- backs the survey
    page's pre-fill of already-answered categories (see PROJECT_NOTES.md)."""
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        r = client.get(f"/candidates/{talent_id}/survey-values", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() == {}  # nothing saved yet

        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {
                    "element_id": "PRACT-SPONSOR", "value": {"requirement": "not_required"},
                    "value_status": "answered", "source_type": "self_report",
                },
            ],
        })
        assert r.status_code == 201, r.text

        r = client.get(f"/candidates/{talent_id}/survey-values", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["PRACT-SPONSOR"]["value"] == {"requirement": "not_required"}
        assert body["PRACT-SPONSOR"]["value_status"] == "answered"

        # Re-submitting the same element (a new version) must return the
        # LATEST value, not the original -- confirms real dedup, not a fluke
        # of only one version existing.
        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {
                    "element_id": "PRACT-SPONSOR", "value": {"requirement": "required"},
                    "value_status": "answered", "source_type": "self_report",
                },
            ],
        })
        assert r.status_code == 201, r.text

        r = client.get(f"/candidates/{talent_id}/survey-values", headers=headers)
        assert r.json()["PRACT-SPONSOR"]["value"] == {"requirement": "required"}

        r = client.get(f"/candidates/{talent_id}/completion")
        assert r.status_code == 401, r.text
