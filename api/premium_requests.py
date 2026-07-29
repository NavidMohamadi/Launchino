"""Candidate Premium access requests: request-and-manually-approve only, no
real payment integration (see PROJECT_NOTES.md / the profile-dashboard task
this was built under). Same shape as api/admin_review.py's queues: a list +
resolve pair per queue, business logic here, api/routers/admin_review.py
wires it to HTTP + the existing admin auth.

Approving a request reuses api/candidate_service.py's
set_candidate_subscription (the same function the admin manual-subscription-
toggle endpoint calls) rather than writing to talent.job_discovery_subscription
a second, separate way.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from schemas import JobDiscoverySubscription, SubscriptionSource

from api.candidate_service import set_candidate_subscription

PLAN_DURATIONS: Dict[str, timedelta] = {
    "one_month": timedelta(days=30),
    "three_month": timedelta(days=90),
}


class PremiumRequestError(ValueError):
    pass


def _row_out(row) -> Dict[str, Any]:
    return {
        "request_id": str(row["request_id"]), "talent_id": str(row["talent_id"]),
        "plan": row["plan"], "status": row["status"], "requested_at": row["requested_at"].isoformat(),
    }


def create_premium_request(conn: Connection, talent_id: UUID, *, plan: str) -> Dict[str, Any]:
    if plan not in PLAN_DURATIONS:
        raise PremiumRequestError(f"plan must be 'one_month' or 'three_month', got {plan!r}")

    existing = conn.execute(
        text(
            "select 1 from premium_access_request where talent_id = :talent_id and status = 'pending'"
        ),
        {"talent_id": str(talent_id)},
    ).first()
    if existing:
        raise PremiumRequestError("pending_exists")

    request_id = uuid.uuid4()
    conn.execute(
        text(
            "insert into premium_access_request (request_id, talent_id, plan) "
            "values (:request_id, :talent_id, :plan)"
        ),
        {"request_id": str(request_id), "talent_id": str(talent_id), "plan": plan},
    )
    row = conn.execute(
        text("select * from premium_access_request where request_id = :id"), {"id": str(request_id)}
    ).mappings().first()
    return _row_out(row)


def get_pending_request_for_candidate(conn: Connection, talent_id: UUID) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            "select * from premium_access_request where talent_id = :talent_id and status = 'pending' "
            "order by requested_at desc limit 1"
        ),
        {"talent_id": str(talent_id)},
    ).mappings().first()
    return _row_out(row) if row else None


def list_pending_requests(conn: Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select r.request_id, r.talent_id, r.plan, r.status, r.requested_at, t.full_name, t.email
            from premium_access_request r
            join talent t on t.talent_id = r.talent_id
            where r.status = 'pending'
            order by r.requested_at
            """
        )
    ).mappings().all()
    return [
        {
            "request_id": str(r["request_id"]), "talent_id": str(r["talent_id"]),
            "full_name": r["full_name"], "email": r["email"], "plan": r["plan"],
            "requested_at": r["requested_at"].isoformat(),
        }
        for r in rows
    ]


def resolve_premium_request(conn: Connection, request_id: UUID, *, decision: str, reviewed_by: str) -> Dict[str, Any]:
    row = conn.execute(
        text("select * from premium_access_request where request_id = :id"), {"id": str(request_id)}
    ).mappings().first()
    if not row:
        raise PremiumRequestError("not_found")
    if row["status"] != "pending":
        raise PremiumRequestError(f"already resolved (status={row['status']})")

    updated_talent = None
    if decision == "approve":
        new_status = "approved"
        expires_at = datetime.now(timezone.utc) + PLAN_DURATIONS[row["plan"]]
        updated_talent = set_candidate_subscription(
            conn, row["talent_id"],
            job_discovery_subscription=JobDiscoverySubscription.ACTIVE,
            subscription_expires_at=expires_at,
            subscription_source=SubscriptionSource.PREMIUM_REQUEST_APPROVED,
        )
    elif decision == "deny":
        new_status = "denied"
    else:
        raise PremiumRequestError(f"decision must be 'approve' or 'deny', got {decision!r}")

    conn.execute(
        text(
            "update premium_access_request set status = :status, reviewed_by = :reviewed_by, reviewed_at = now() "
            "where request_id = :request_id"
        ),
        {"status": new_status, "reviewed_by": reviewed_by, "request_id": str(request_id)},
    )

    result: Dict[str, Any] = {"request_id": str(request_id), "status": new_status}
    if updated_talent is not None:
        result["talent"] = {
            "talent_id": str(updated_talent["talent_id"]),
            "job_discovery_subscription": updated_talent["job_discovery_subscription"],
            "subscription_expires_at": updated_talent["subscription_expires_at"].isoformat()
            if updated_talent["subscription_expires_at"] else None,
            "subscription_source": updated_talent["subscription_source"],
        }
    return result
