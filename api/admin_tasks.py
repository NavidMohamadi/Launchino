"""Admin-triggered "Run now" actions for manual/recurring processes,
replacing CLI-only access (see PROJECT_NOTES.md). Every run tracked here
originates from an explicit admin click (POST /admin/tasks/{task_name}/run,
api/routers/admin_tasks.py) -- nothing in this module runs automatically.
This does not change the "never auto-runs" principle
api/reference_data_refresh.py / api/job_discovery_scheduler.py /
api/job_discovery_runner.py each already state in their own docstrings; it
only adds a button in front of the same functions those scripts already
exposed via the CLI, not a scheduler.

Runs execute via FastAPI's BackgroundTasks (wired in the router), so the
triggering HTTP request returns immediately ("started at ...") rather than
blocking for however long the real work takes -- ESCO alone is ~135
paginated API calls, and the job discovery pipeline makes real, billable
Claude API calls per subscribed candidate. The three underlying modules are
imported lazily (inside each run_*_task function, not at the top of this
file) specifically so importing this module -- and therefore api/main.py
starting up -- never pulls in httpx clients/adapters/AI clients as a side
effect; they're only actually loaded the first time an admin clicks Run now.

Background functions here must NOT reuse the request's own `conn` -- that
connection's transaction is tied to the request/response cycle and may
already be closed by the time the background task actually executes (it
runs after the response is sent). Each run_*_task function below opens its
own fresh connection from api.database.engine.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.database import engine

# Known, fixed set of triggerable task_names -- matches admin_task_run's own
# check constraint (migrations/007_v2_3_0_to_v2_4_0.sql).
TASK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "reference_refresh_ror": {"label": "Reference data: ROR institutions", "dataset": "ror"},
    "reference_refresh_esco": {"label": "Reference data: ESCO skills/occupations", "dataset": "esco"},
    "reference_refresh_croho": {"label": "Reference data: DUO/CROHO programmes", "dataset": "croho"},
    "ingestion_poll": {"label": "Job board ingestion poll cycle", "dataset": None},
    "job_discovery_run": {"label": "Job Discovery recommendation pipeline", "dataset": None},
}

REFERENCE_REFRESH_TASK_NAMES = ["reference_refresh_ror", "reference_refresh_esco", "reference_refresh_croho"]

# ISCED-F 2013 is a static, hand-transcribed bundle with no refresh mechanism
# at all (see api/reference_data_refresh.py's own module docstring) -- shown
# in the dashboard as a status-only row (no Run-now button), not silently
# omitted and not given a fake button that would do nothing.
ISCED_F_STATUS_ENTRY = {
    "task_name": "reference_isced_f", "label": "Reference data: ISCED-F 2013", "refreshable": False,
    "status": "static", "started_at": None, "completed_at": None, "triggered_by": None,
    "result_summary": None, "error_message": None,
    "note": "Fixed international standard (UNESCO ISCED-F 2013); hand-transcribed once, no refresh mechanism exists.",
}

# A 'running' row older than this is treated as interrupted (e.g. the server
# process restarted mid-run) rather than trusted forever -- otherwise a
# single crash would permanently block that task from ever running again,
# since the "already running" check would never see it finish.
STALE_RUNNING_THRESHOLD = timedelta(minutes=30)


class TaskAlreadyRunningError(RuntimeError):
    pass


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _to_plain(value: Any) -> Any:
    """Recursively converts dataclasses/enums/UUIDs/datetimes into JSON-safe
    plain values, so a real dataclass report (PollCycleReport,
    JobDiscoveryBatchMetrics, ...) can be stored directly in
    admin_task_run.result_summary without hand-writing a serializer per
    report shape."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, (UUID, datetime)):
        return str(value)
    return value


def _reap_stale_running_rows(conn: Connection) -> None:
    conn.execute(
        text(
            """
            update admin_task_run
            set status = 'failed', completed_at = now(),
                error_message = 'Interrupted -- no completion recorded within the expected window (the server process likely restarted mid-run).'
            where status = 'running' and started_at < :cutoff
            """
        ),
        {"cutoff": datetime.now(timezone.utc) - STALE_RUNNING_THRESHOLD},
    )


def _latest_runs(conn: Connection) -> Dict[str, Dict[str, Any]]:
    _reap_stale_running_rows(conn)
    rows = conn.execute(
        text(
            """
            select distinct on (task_name) task_name, task_run_id, status, started_at, completed_at,
                   triggered_by, result_summary, error_message
            from admin_task_run
            order by task_name, started_at desc
            """
        )
    ).mappings().all()
    return {row["task_name"]: dict(row) for row in rows}


def get_task_status(conn: Connection) -> List[Dict[str, Any]]:
    latest = _latest_runs(conn)
    result: List[Dict[str, Any]] = []
    for task_name, meta in TASK_DEFINITIONS.items():
        run = latest.get(task_name)
        if run:
            result.append({
                "task_name": task_name, "label": meta["label"], "refreshable": True,
                "status": run["status"], "started_at": run["started_at"], "completed_at": run["completed_at"],
                "triggered_by": run["triggered_by"], "result_summary": _as_json(run["result_summary"]),
                "error_message": run["error_message"],
            })
        else:
            result.append({
                "task_name": task_name, "label": meta["label"], "refreshable": True,
                "status": "never_run", "started_at": None, "completed_at": None,
                "triggered_by": None, "result_summary": None, "error_message": None,
            })
    result.append(dict(ISCED_F_STATUS_ENTRY))
    return result


def start_task_run(conn: Connection, task_name: str, *, triggered_by: Optional[str]) -> UUID:
    if task_name not in TASK_DEFINITIONS:
        raise ValueError(f"Unknown task_name: {task_name}")
    _reap_stale_running_rows(conn)
    existing = conn.execute(
        text("select 1 from admin_task_run where task_name = :task_name and status = 'running'"),
        {"task_name": task_name},
    ).first()
    if existing:
        raise TaskAlreadyRunningError(f"{task_name} is already running")
    task_run_id = uuid4()
    conn.execute(
        text(
            """
            insert into admin_task_run (task_run_id, task_name, status, triggered_by)
            values (:task_run_id, :task_name, 'running', :triggered_by)
            """
        ),
        {"task_run_id": str(task_run_id), "task_name": task_name, "triggered_by": triggered_by},
    )
    return task_run_id


def _finish_task_run(
    task_run_id: UUID, *, status: str, result_summary: Optional[Any] = None, error_message: Optional[str] = None,
) -> None:
    # Opens its own connection deliberately -- see module docstring. Called
    # from a background task, well after the triggering request's own
    # connection has been committed and returned to the pool.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                update admin_task_run
                set status = :status, completed_at = now(), result_summary = cast(:result_summary as jsonb),
                    error_message = :error_message
                where task_run_id = :task_run_id
                """
            ),
            {
                "task_run_id": str(task_run_id), "status": status,
                "result_summary": json.dumps(_to_plain(result_summary)) if result_summary is not None else None,
                "error_message": error_message,
            },
        )


# --- Background-safe runner wrappers (each opens its own connection) ------

def run_reference_refresh_task(task_run_id: UUID, dataset: str) -> None:
    from api.reference_data_refresh import REFRESH_FUNCTIONS  # lazy -- see module docstring
    try:
        result = REFRESH_FUNCTIONS[dataset]()
        _finish_task_run(task_run_id, status="succeeded", result_summary=result)
    except Exception as exc:
        _finish_task_run(task_run_id, status="failed", error_message=str(exc)[:2000])


def run_ingestion_poll_task(task_run_id: UUID) -> None:
    from api.job_discovery_scheduler import run_poll_cycle  # lazy -- see module docstring
    try:
        with engine.begin() as conn:
            report = run_poll_cycle(conn)
        _finish_task_run(task_run_id, status="succeeded", result_summary=report)
    except Exception as exc:
        _finish_task_run(task_run_id, status="failed", error_message=str(exc)[:2000])


def run_job_discovery_task(task_run_id: UUID) -> None:
    from api.job_discovery_runner import run_real_job_discovery_cycle  # lazy -- see module docstring
    try:
        with engine.begin() as conn:
            result = run_real_job_discovery_cycle(conn)
        summary = {"batch_run_id": str(result["batch_run_id"]), "metrics": result["output"].metrics}
        _finish_task_run(task_run_id, status="succeeded", result_summary=summary)
    except Exception as exc:
        _finish_task_run(task_run_id, status="failed", error_message=str(exc)[:2000])
