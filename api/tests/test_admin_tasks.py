"""Real API + DB tests for the admin task-runner feature (Item 1: "Run now"
buttons for manual/recurring processes -- api/admin_tasks.py,
api/routers/admin_tasks.py). See PROJECT_NOTES.md.

Admin auth: issues a token directly via api.auth.create_access_token, same
convention as test_admin_review.py -- no plaintext admin password needed.

One test (test_reference_refresh_croho_real_trigger_end_to_end) makes a real,
live HTTP call to DUO's public dataset -- chosen deliberately as the
cheapest real end-to-end path (a single small CSV download), unlike ROR
(a large Zenodo zip) or ESCO (~135 paginated calls) or the job discovery
pipeline (real, billable Claude API calls per candidate). FastAPI's
TestClient runs BackgroundTasks synchronously before the request call
returns, so this test can assert on the final "succeeded" status directly,
even though in production the same endpoint returns before the task finishes.
In practice this test still polls briefly rather than assuming synchronous
completion -- background-task scheduling timing isn't a documented FastAPI
contract worth hard-coding an assumption around, and polling is exactly what
the real dashboard does too.
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
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


def _delete_task_runs(task_run_ids):
    if not task_run_ids:
        return
    with engine.begin() as conn:
        conn.execute(
            text("delete from admin_task_run where task_run_id = any(:ids)"),
            {"ids": [str(i) for i in task_run_ids]},
        )


def test_task_status_shape_and_isced_static():
    with TestClient(app) as client:
        r = client.get("/admin/tasks/status", headers=_admin_headers())
        assert r.status_code == 200, r.text
        rows = {row["task_name"]: row for row in r.json()}

    for name in [
        "reference_refresh_ror", "reference_refresh_esco", "reference_refresh_croho",
        "ingestion_poll", "job_discovery_run",
    ]:
        assert name in rows, rows.keys()
        assert rows[name]["refreshable"] is True
        assert rows[name]["status"] in ("never_run", "running", "succeeded", "failed")

    isced = rows["reference_isced_f"]
    assert isced["refreshable"] is False
    assert isced["status"] == "static"
    assert "note" in isced and isced["note"]


def test_unknown_task_name_returns_404():
    with TestClient(app) as client:
        r = client.post("/admin/tasks/not_a_real_task/run", headers=_admin_headers())
    assert r.status_code == 404, r.text


def test_already_running_task_returns_409():
    task_run_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into admin_task_run (task_run_id, task_name, status, triggered_by)
                values (:id, 'ingestion_poll', 'running', 'test-setup')
                """
            ),
            {"id": str(task_run_id)},
        )
    try:
        with TestClient(app) as client:
            r = client.post("/admin/tasks/ingestion_poll/run", headers=_admin_headers())
        assert r.status_code == 409, r.text
    finally:
        _delete_task_runs([task_run_id])


def test_stale_running_row_is_reaped_before_status_or_trigger():
    task_run_id = uuid.uuid4()
    stale_started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into admin_task_run (task_run_id, task_name, status, started_at, triggered_by)
                values (:id, 'job_discovery_run', 'running', :started_at, 'test-setup')
                """
            ),
            {"id": str(task_run_id), "started_at": stale_started_at},
        )
    try:
        with TestClient(app) as client:
            r = client.get("/admin/tasks/status", headers=_admin_headers())
        assert r.status_code == 200, r.text
        rows = {row["task_name"]: row for row in r.json()}
        assert rows["job_discovery_run"]["status"] == "failed"
        assert "Interrupted" in rows["job_discovery_run"]["error_message"]
    finally:
        _delete_task_runs([task_run_id])


def test_reference_refresh_croho_real_trigger_end_to_end():
    task_run_id = None
    try:
        with TestClient(app) as client:
            r = client.post("/admin/tasks/reference_refresh_croho/run", headers=_admin_headers())
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["task_name"] == "reference_refresh_croho"
            assert body["status"] == "running"
            task_run_id = uuid.UUID(body["task_run_id"])

            croho = None
            for _ in range(30):
                r = client.get("/admin/tasks/status", headers=_admin_headers())
                assert r.status_code == 200, r.text
                rows = {row["task_name"]: row for row in r.json()}
                croho = rows["reference_refresh_croho"]
                if croho["status"] != "running":
                    break
                time.sleep(1)

        assert croho["status"] == "succeeded", croho
        assert croho["triggered_by"]
        assert croho["result_summary"]["count"] > 0
    finally:
        _delete_task_runs([task_run_id])


def test_run_all_reference_refresh_skips_already_running(monkeypatch):
    # Stubs out the real refresh work (esco alone is ~135 paginated calls) --
    # this test is only about the started-vs-skipped bookkeeping, which the
    # dedicated real end-to-end croho test above already exercises for real.
    from api import admin_tasks

    monkeypatch.setattr(admin_tasks, "run_reference_refresh_task", lambda task_run_id, dataset: None)

    existing_run_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into admin_task_run (task_run_id, task_name, status, triggered_by)
                values (:id, 'reference_refresh_ror', 'running', 'test-setup')
                """
            ),
            {"id": str(existing_run_id)},
        )
    started_ids = []
    try:
        with TestClient(app) as client:
            r = client.post("/admin/tasks/reference-refresh/run-all", headers=_admin_headers())
        assert r.status_code == 200, r.text
        body = r.json()
        assert "reference_refresh_ror" in body["skipped_already_running"]
        started_names = {item["task_name"] for item in body["started"]}
        assert started_names == {"reference_refresh_esco", "reference_refresh_croho"}
        started_ids = [uuid.UUID(item["task_run_id"]) for item in body["started"]]
    finally:
        _delete_task_runs([existing_run_id, *started_ids])
