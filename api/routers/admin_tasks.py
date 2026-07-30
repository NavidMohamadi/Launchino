"""Admin-triggered "Run now" endpoints for manual/recurring processes (see
api/admin_tasks.py and PROJECT_NOTES.md). Every POST here starts exactly one
background task from an explicit admin click -- nothing runs on a schedule.

The mutating endpoints below open their own `with engine.begin() as conn:`
block instead of using the shared `Depends(get_connection)` request-scoped
connection. This matters here specifically: FastAPI documents that a
yield-dependency's post-yield cleanup (which is where get_connection commits
its transaction) runs *after* any scheduled BackgroundTasks execute, not
before. If start_task_run's insert used that dependency, the background
task's own fresh connection (api.admin_tasks._finish_task_run) would try to
UPDATE a row that the inserting transaction hadn't committed yet -- a silent
no-op update, not an error, leaving the row stuck at status='running'
forever (caught by a real end-to-end test, see api/tests/test_admin_tasks.py).
Opening and closing the connection inline inside the route function body
commits it before the function returns, well before BackgroundTasks run.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api import admin_tasks
from api.auth import require_role
from api.config import ADMIN_EMAIL
from api.database import engine

router = APIRouter(prefix="/admin", tags=["admin-tasks"], dependencies=[Depends(require_role("admin"))])


@router.get("/tasks/status")
def get_tasks_status() -> list:
    with engine.begin() as conn:
        return admin_tasks.get_task_status(conn)


def _schedule(background_tasks: BackgroundTasks, task_name: str, task_run_id) -> None:
    meta = admin_tasks.TASK_DEFINITIONS[task_name]
    if meta["dataset"] is not None:
        background_tasks.add_task(admin_tasks.run_reference_refresh_task, task_run_id, meta["dataset"])
    elif task_name == "ingestion_poll":
        background_tasks.add_task(admin_tasks.run_ingestion_poll_task, task_run_id)
    elif task_name == "job_discovery_run":
        background_tasks.add_task(admin_tasks.run_job_discovery_task, task_run_id)


@router.post("/tasks/{task_name}/run", status_code=202)
def run_task(task_name: str, background_tasks: BackgroundTasks) -> dict:
    try:
        with engine.begin() as conn:
            task_run_id = admin_tasks.start_task_run(conn, task_name, triggered_by=ADMIN_EMAIL)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except admin_tasks.TaskAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule(background_tasks, task_name, task_run_id)
    return {"task_run_id": str(task_run_id), "task_name": task_name, "status": "running"}


@router.post("/tasks/reference-refresh/run-all")
def run_all_reference_refresh(background_tasks: BackgroundTasks) -> dict:
    started = []
    skipped = []
    for task_name in admin_tasks.REFERENCE_REFRESH_TASK_NAMES:
        try:
            with engine.begin() as conn:
                task_run_id = admin_tasks.start_task_run(conn, task_name, triggered_by=ADMIN_EMAIL)
        except admin_tasks.TaskAlreadyRunningError:
            skipped.append(task_name)
            continue
        _schedule(background_tasks, task_name, task_run_id)
        started.append({"task_name": task_name, "task_run_id": str(task_run_id)})
    return {"started": started, "skipped_already_running": skipped}
