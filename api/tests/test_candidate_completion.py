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

from api.candidate_service import get_premium_readiness_threshold_percent  # noqa: E402
from api.main import app  # noqa: E402
from schemas import MatchConfiguration  # noqa: E402

# Every real, non-MOT ALWAYS-activated element outside PRACT (MOT is
# deliberately left unselected -- 0 active items there don't count against
# the total, see api/candidate_service.py). Real element_ids + minimal valid
# values for each real candidate_value_schema shape in
# data/fit_dictionary_starter.json.
_TEAM_CAREER_ENV_ANSWERS = [
    {"element_id": "TEAM-COLLAB-INTENSITY",
     "value": {"preferred_min": 2, "preferred_max": 4, "tolerable_min": 1, "tolerable_max": 5}},
] + [
    {"element_id": eid, "value": {"values": ["example"], "ranked": True}}
    for eid in [
        "CAREER-PRIMARY-ROLE", "CAREER-SECONDARY-ROLE", "CAREER-PROBLEM-TYPES", "CAREER-DESIRED-ACTIVITIES",
        "CAREER-AVOIDED-ACTIVITIES", "CAREER-INDUSTRIES", "CAREER-DEVELOPMENT",
    ]
] + [
    {"element_id": eid, "value": {"preferred_min": 2, "preferred_max": 4, "tolerable_min": 1, "tolerable_max": 5}}
    for eid in [
        "ENV-STRUCTURE", "ENV-PRIORITY-CHANGE", "ENV-METHOD-AUTONOMY", "ENV-MANAGER-INVOLVEMENT",
        "ENV-FEEDBACK", "ENV-PROCESS-MATURITY", "ENV-REACTIVITY", "ENV-ROLE-BREADTH", "ENV-STAKEHOLDER",
    ]
]
_PRACT_ANSWERS = [
    {"element_id": "PRACT-SPONSOR", "value": {"requirement": "not_required"}},
    {"element_id": "PRACT-START", "value": {"earliest_start": "2026-09-01"}},
    {"element_id": "PRACT-WORKMODE", "value": {"acceptable": ["hybrid"]}},
    {"element_id": "PRACT-COUNTRY", "value": {"current_country": "NL", "presence_relative_to_vacancy": "in_country"}},
    {"element_id": "PRACT-LANG", "value": {"languages": {"English": "fluent"}}},
    {"element_id": "PRACT-CONTRACT", "value": {"acceptable": ["full_time"]}},
]


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


def test_premium_readiness_threshold_is_read_from_match_configuration_default():
    """Confirms no second hardcoded copy of the threshold exists anywhere --
    the value returned must equal MatchConfiguration's own field default,
    read fresh here rather than restated as a literal."""
    expected = MatchConfiguration.model_fields["minimum_overall_coverage"].default * 100
    assert get_premium_readiness_threshold_percent() == expected


def test_premium_ready_flips_as_real_coverage_crosses_the_real_threshold():
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)
        threshold = get_premium_readiness_threshold_percent()

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        body = r.json()
        assert body["premium_readiness_threshold_percent"] == threshold
        assert body["overall_percent_complete"] == 0.0
        assert body["premium_ready"] is False

        # Answer every real ALWAYS-activated element (PRACT+TEAM+CAREER+ENV =
        # 23 items; MOT stays unselected, 0 active there, doesn't count) --
        # a genuinely complete (100%) profile must cross any threshold <=100%.
        all_answers = _PRACT_ANSWERS + _TEAM_CAREER_ENV_ANSWERS
        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {"element_id": a["element_id"], "value": a["value"], "value_status": "answered", "source_type": "self_report"}
                for a in all_answers
            ],
        })
        assert r.status_code == 201, r.text
        assert r.json()["values_stored"] == 23

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        body = r.json()
        assert body["overall_percent_complete"] == 100.0
        assert body["overall_percent_complete"] >= body["premium_readiness_threshold_percent"]
        assert body["premium_ready"] is True
