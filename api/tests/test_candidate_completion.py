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
from sqlalchemy import text  # noqa: E402

from api.candidate_service import get_premium_readiness_threshold_percent  # noqa: E402
from api.database import engine  # noqa: E402
from api.main import app  # noqa: E402
from schemas import MatchConfiguration  # noqa: E402

# Every real, non-MOT ALWAYS-activated element outside PRACT (MOT is
# deliberately left unselected -- 0 active items there don't count against
# the total, see api/candidate_service.py). Real element_ids + minimal valid
# values for each real candidate_value_schema shape in
# data/fit_dictionary_starter.json.
#
# CAREER-PROBLEM-TYPES/DESIRED-ACTIVITIES/AVOIDED-ACTIVITIES are deliberately
# absent (v3 redesign, see PROJECT_NOTES.md): deactivated (active=false), so
# they're excluded from load_dictionary entirely and would never count here
# even if answered. CAREER-PRIMARY-ROLE/SECONDARY-ROLE/CAREER-INDUSTRIES use
# their new structured ESCO/NACE shapes, not the old free-text "values" list.
_TEAM_CAREER_ENV_ANSWERS = [
    {"element_id": "TEAM-COLLAB-INTENSITY", "value": {"level": 3}},
    {"element_id": "CAREER-PRIMARY-ROLE", "value": {
        "occupation": {"raw_text": "Software Engineer", "esco_uri": None, "label": None, "confidence": None},
        "still_exploring": False, "open_to_adjacent": False,
    }},
    {"element_id": "CAREER-SECONDARY-ROLE", "value": {
        "occupation": {"raw_text": "Data Analyst", "esco_uri": None, "label": None, "confidence": None},
        "still_exploring": False, "open_to_adjacent": False,
    }},
    {"element_id": "CAREER-INDUSTRIES", "value": {
        "industries": [{"raw_text": "Technology", "nace_code": None, "label": None, "confidence": None}],
    }},
    {"element_id": "CAREER-DEVELOPMENT", "value": {"values": ["example"], "ranked": True}},
    {"element_id": "CAREER-NARRATIVE", "value": {"text": "Would like more architecture work, less on-call."}},
] + [
    {"element_id": eid, "value": {"level": 3}}
    for eid in [
        "ENV-STRUCTURE", "ENV-PRIORITY-CHANGE", "ENV-METHOD-AUTONOMY", "ENV-MANAGER-INVOLVEMENT",
        "ENV-FEEDBACK", "ENV-PROCESS-MATURITY", "ENV-REACTIVITY", "ENV-ROLE-BREADTH", "ENV-STAKEHOLDER",
    ]
] + [
    {"element_id": eid, "value": {"level": 3}}
    for eid in ["ENV-PRECISION", "ENV-IDEA-EXECUTION", "ENV-NOVELTY", "ENV-COMMUNICATION-DIRECTNESS"]
] + [
    {"element_id": eid, "value": {"level": 3}}
    for eid in [
        "CAREER-INTEREST-REALISTIC", "CAREER-INTEREST-INVESTIGATIVE", "CAREER-INTEREST-ARTISTIC",
        "CAREER-INTEREST-SOCIAL", "CAREER-INTEREST-ENTERPRISING", "CAREER-INTEREST-CONVENTIONAL",
    ]
]
_PRACT_ANSWERS = [
    {"element_id": "PRACT-SPONSOR", "value": {"requirement": "not_required"}},
    {"element_id": "PRACT-START", "value": {"earliest_start": "2026-09-01"}},
    {"element_id": "PRACT-WORKMODE", "value": {"acceptable": ["hybrid"]}},
    {"element_id": "PRACT-COUNTRY", "value": {"current_country": "NL", "presence_relative_to_vacancy": "in_country"}},
    {"element_id": "PRACT-LANG", "value": {"languages": {"English": "fluent"}}},
    {"element_id": "PRACT-CONTRACT", "value": {"acceptable": ["full_time"]}},
    {"element_id": "PRACT-WORKTYPE", "value": {"acceptable": ["full_time"]}},
]
# Phase 4: EDU/CAP/TASK real ALWAYS-activated elements. TASK-YEARS is
# deliberately absent -- it's computed automatically from TASK-EXPERIENCE's
# dates (see src/task_years.py), never submitted directly.
_EDU_CAP_TASK_ANSWERS = [
    {"element_id": "EDU-HISTORY", "value": {"entries": [{
        "level": "bachelor", "institution": {"ror_id": None, "name": "Test University"},
        "program": "Computer Science", "field": {"isced_code": None, "confidence": None},
        "start_date": "2015-01-01", "end_date": "2019-01-01", "status": "completed",
    }]}},
    {"element_id": "CAP-SKILLS", "value": {"skills": [
        {"skill": "SQL", "level": "advanced", "esco_uri": None, "confidence": None},
    ]}},
    {"element_id": "TASK-EXPERIENCE", "value": {"jobs": [
        {"job_title": "Software Engineer", "esco_uri": None, "confidence": None,
         "start_date": "2019-06-01", "end_date": None, "current": True},
    ]}},
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
        assert set(by_category) == {"PRACT", "TEAM", "CAREER", "MOT", "ENV", "EDU", "CAP", "TASK"}
        # contact_preference has no DB default -- a fresh candidate has never
        # made a real choice yet, so Account Settings is correctly incomplete
        # from registration (see PROJECT_NOTES.md for the earlier bug where a
        # default 'email' made this indistinguishable from a genuine choice).
        assert body["basic_info"] == {"label": "Account Settings", "complete": False}
        assert body["dashboard_intro_seen"] is False
        pract = by_category["PRACT"]
        assert pract["label"] == "Practical fit"
        assert pract["status"] == "not_started"
        assert pract["percent_complete"] == 0.0
        assert pract["active_item_count"] == 7  # 7 real ALWAYS-activated PRACT elements (incl. PRACT-WORKTYPE, Phase 4)

        # Answer 3 of PRACT's 7 real elements -- real values, real schema keys.
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
        assert pract["active_item_count"] == 7
        assert pract["percent_complete"] == round(3 / 7 * 100, 1)
        # Untouched categories are still genuinely not_started, not a stale default.
        assert by_category["ENV"]["status"] == "not_started"

        # Answer the remaining 4 PRACT elements -> category flips to complete.
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
                    "element_id": "PRACT-WORKTYPE", "value": {"acceptable": ["full_time"]},
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


def test_basic_info_complete_is_conditional_on_contact_preference():
    """Account Settings must only be "complete" once the candidate has made
    a genuine contact_preference choice, and (if that choice is 'phone') has
    actually provided a phone number -- mirrors set_candidate_basic_info's
    own write-side validation rule. Confirms the fix for a real bug where
    contact_preference defaulted to 'email' at the DB level, making a
    default indistinguishable from a real choice (see PROJECT_NOTES.md)."""
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        # Fresh candidate: contact_preference has no DB default, genuinely
        # unset -- correctly incomplete, not "complete because nothing's
        # required yet."
        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["basic_info"]["complete"] is False

        # Making a real, deliberate non-phone choice completes it -- no
        # phone number needed for 'email'.
        r = client.patch(
            f"/candidates/{talent_id}/basic-info", headers=headers, json={"contact_preference": "email"},
        )
        assert r.status_code == 200, r.text
        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["basic_info"]["complete"] is True

        # Setting contact_preference to 'phone' together with a real phone
        # number in the same request -- the only way the write-side
        # validation allows reaching 'phone' at all -- stays complete.
        r = client.patch(
            f"/candidates/{talent_id}/basic-info", headers=headers,
            json={"phone": "+31 6 1234 5678", "contact_preference": "phone"},
        )
        assert r.status_code == 200, r.text
        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["basic_info"]["complete"] is True

        # set_candidate_basic_info's own guard makes contact_preference='phone'
        # with no phone number unreachable through the API once phone is ever
        # set (a None update is dropped as "no change", never a clear) -- so
        # this edge case (e.g. data from before that guard existed) is
        # simulated directly at the DB level to confirm the read side still
        # correctly flags it as incomplete, not just trusts a stale True.
        with engine.begin() as conn:
            conn.execute(
                text("update talent set phone = null where talent_id = :talent_id"),
                {"talent_id": talent_id},
            )
        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["basic_info"]["complete"] is False


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

        # Answer every real ALWAYS-activated element (PRACT 7 + TEAM/CAREER/ENV
        # 25 [v3 redesign: 1 TEAM + 5 CAREER + 9 old ENV + 4 new ENV + 6 RIASEC]
        # + EDU/CAP/TASK 3 = 35 submitted items; MOT stays unselected, 0 active
        # there, doesn't count) -- a genuinely complete (100%) profile must
        # cross any threshold <=100%. TASK-YEARS isn't submitted directly (see
        # _EDU_CAP_TASK_ANSWERS's own comment) but is auto-derived from
        # TASK-EXPERIENCE, so values_stored is 36, one more than submitted.
        all_answers = _PRACT_ANSWERS + _TEAM_CAREER_ENV_ANSWERS + _EDU_CAP_TASK_ANSWERS
        r = client.post(f"/candidates/{talent_id}/survey", headers=headers, json={
            "values": [
                {"element_id": a["element_id"], "value": a["value"], "value_status": "answered", "source_type": "self_report"}
                for a in all_answers
            ],
        })
        assert r.status_code == 201, r.text
        assert r.json()["values_stored"] == 36

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        body = r.json()
        assert body["overall_percent_complete"] == 100.0
        assert body["overall_percent_complete"] >= body["premium_readiness_threshold_percent"]
        assert body["premium_ready"] is True


def test_dashboard_intro_seen_flips_true_and_is_idempotent():
    with TestClient(app) as client:
        talent_id, headers = _make_candidate(client)

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["dashboard_intro_seen"] is False

        r = client.post(f"/candidates/{talent_id}/dashboard-intro-seen", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"talent_id": talent_id, "dashboard_intro_seen": True}

        r = client.get(f"/candidates/{talent_id}/completion", headers=headers)
        assert r.json()["dashboard_intro_seen"] is True

        # Idempotent -- marking it again is a harmless no-op, not an error.
        r = client.post(f"/candidates/{talent_id}/dashboard-intro-seen", headers=headers)
        assert r.status_code == 200, r.text
