"""Admin-only review queues (Phase 2): dedup review, sponsor-match review,
extraction spot-check. Each function here calls into existing, unmodified
decision logic (vacancy_merge.py's merge_profile_fields,
CompanySponsorshipSignal's own model_validator) rather than reimplementing it.

api/routers/admin_review.py wires these to HTTP + the existing admin auth.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from source_schemas import CompanySponsorshipSignal, SourceTrustLevel, SponsorMatchMethod, VerificationStatus
from vacancy_merge import merge_profile_fields

from api.ingestion_store import link_vacancy_snapshot
from api.vacancy_store import fetch_vacancy, upsert_vacancy


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


# --- 1. Duplicate-review queue (vacancy_dedup_review) --------------------

def list_pending_dedup_reviews(conn: Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select r.review_id, r.incoming_snapshot_id, r.candidate_vacancy_id, r.decision_reason,
                   r.confidence, r.status, r.created_at,
                   v.role_title, v.company_name, v.location_text, v.lifecycle_status,
                   s.source_id, s.source_url, s.retrieved_at, s.trust_level
            from vacancy_dedup_review r
            join vacancy v on v.vacancy_id = r.candidate_vacancy_id
            join source_snapshot s on s.snapshot_id = r.incoming_snapshot_id
            where r.status = 'pending'
            order by r.created_at
            """
        )
    ).mappings().all()
    return [
        {
            "review_id": str(r["review_id"]),
            "incoming_snapshot_id": r["incoming_snapshot_id"],
            "candidate_vacancy_id": str(r["candidate_vacancy_id"]),
            "decision_reason": r["decision_reason"],
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "created_at": r["created_at"].isoformat(),
            "existing_vacancy": {
                "title": r["role_title"], "company_name": r["company_name"],
                "location_text": r["location_text"], "lifecycle_status": r["lifecycle_status"],
            },
            "incoming_source": {
                "source_id": r["source_id"], "source_url": r["source_url"],
                "retrieved_at": r["retrieved_at"].isoformat() if r["retrieved_at"] else None,
                "trust_level": r["trust_level"],
            },
        }
        for r in rows
    ]


class DedupReviewError(ValueError):
    pass


def resolve_dedup_review(
    conn: Connection, review_id: UUID, *, decision: str, note: Optional[str], resolved_by: str,
) -> Dict[str, Any]:
    review = conn.execute(
        text("select * from vacancy_dedup_review where review_id = :id"), {"id": str(review_id)}
    ).mappings().first()
    if not review:
        raise DedupReviewError("not_found")
    if review["status"] != "pending":
        raise DedupReviewError(f"already resolved (status={review['status']})")

    if decision == "duplicate":
        new_status = "merge"
        snapshot = conn.execute(
            text("select * from source_snapshot where snapshot_id = :id"),
            {"id": review["incoming_snapshot_id"]},
        ).mappings().first()
        existing = fetch_vacancy(conn, review["candidate_vacancy_id"])
        if snapshot and existing:
            # incoming_fields is deliberately {}: merge_profile_fields (unmodified,
            # reused as-is) needs the incoming posting's re-parsed structured fields
            # (title, description_text, ...) to do real field-precedence merging, but
            # that parsing only exists inline inside each adapter's live fetch() --
            # there's no standalone "parse this stored raw_payload" function to call
            # for a snapshot captured in an earlier poll cycle. Calling the real
            # merge function with no new field content is still a genuine, correct
            # use of it (it appends incoming_snapshot_id, bumps verification_status
            # if higher-ranked, and correctly does NOT report a content change) --
            # it just can't refine title/description/etc. without re-deriving them,
            # which would mean duplicating each adapter's parsing logic here. See
            # PROJECT_NOTES.md.
            merged = merge_profile_fields(
                existing, incoming_fields={}, incoming_snapshot_id=snapshot["snapshot_id"],
                incoming_trust=SourceTrustLevel(snapshot["trust_level"]),
                incoming_verification=VerificationStatus.SOURCE_VERIFIED,
            )
            if snapshot["external_job_id"] and snapshot["source_id"] not in merged.external_job_ids:
                merged.external_job_ids[snapshot["source_id"]] = snapshot["external_job_id"]
            upsert_vacancy(conn, merged)
            link_vacancy_snapshot(conn, vacancy_id=merged.vacancy_id, snapshot_id=snapshot["snapshot_id"], is_primary=False)
    elif decision == "not_duplicate":
        # "Keep both as separate vacancies" is the recorded decision; it does not
        # automatically materialise the incoming snapshot as its own new vacancy
        # row today, for the same re-parsing limitation noted above -- a distinct
        # vacancy needs real title/description content, not just a snapshot
        # reference. See PROJECT_NOTES.md for the proposed fix (a standalone
        # parse-row function per adapter).
        new_status = "create_separate"
    else:
        raise DedupReviewError(f"decision must be 'duplicate' or 'not_duplicate', got {decision!r}")

    conn.execute(
        text(
            """
            update vacancy_dedup_review
            set status = :status, reviewed_by = :reviewed_by, reviewed_at = now(), review_note = :note
            where review_id = :review_id
            """
        ),
        {"status": new_status, "reviewed_by": resolved_by, "note": note, "review_id": str(review_id)},
    )
    return {"review_id": str(review_id), "status": new_status}


# --- 2. Sponsor-match review (vacancy.sponsorship_signal) ----------------
# See PROJECT_NOTES.md: nothing in the real ingestion pipeline ever calls
# src/ind_sponsor_registry.py's SponsorRegistry.lookup(), so this column is
# never actually populated for any real vacancy today. This queries the real,
# correct, forward-compatible storage location -- it will start returning rows
# the moment that wiring gap is closed, with no change needed here.

def list_pending_sponsor_reviews(conn: Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select vacancy_id, role_title, company_name, company_domain, sponsorship_signal
            from vacancy
            where sponsorship_signal is not null
              and (
                coalesce((sponsorship_signal->>'possible_match')::boolean, false)
                or coalesce((sponsorship_signal->>'human_review_required')::boolean, false)
              )
            order by vacancy_id
            """
        )
    ).mappings().all()
    return [
        {
            "vacancy_id": str(r["vacancy_id"]), "title": r["role_title"], "company_name": r["company_name"],
            "company_domain": r["company_domain"], "sponsorship_signal": _as_json(r["sponsorship_signal"]),
        }
        for r in rows
    ]


class SponsorReviewError(ValueError):
    pass


def resolve_sponsor_review(conn: Connection, vacancy_id: UUID, *, decision: str, note: Optional[str]) -> Dict[str, Any]:
    row = conn.execute(
        text("select sponsorship_signal from vacancy where vacancy_id = :id"), {"id": str(vacancy_id)}
    ).mappings().first()
    if not row:
        raise SponsorReviewError("not_found")
    current = _as_json(row["sponsorship_signal"]) or {}

    if decision == "confirm":
        # match_method_integrity (CompanySponsorshipSignal's own model_validator,
        # unmodified) sets recognised_sponsor=True/possible_match=False whenever
        # match_method is an exact method -- the real "verified" trust level is
        # applied by the model itself, not reimplemented here.
        signal = CompanySponsorshipSignal(
            match_method=SponsorMatchMethod.EXACT_LEGAL_NAME,
            matched_organisation_name=current.get("matched_organisation_name"),
            match_confidence=current.get("match_confidence"),
            registry_name=current.get("registry_name", "IND public register Work"),
            registry_snapshot_date=current.get("registry_snapshot_date"),
            note=note or "Confirmed by admin after manual review of the fuzzy match.",
        )
    elif decision == "reject":
        signal = CompanySponsorshipSignal(
            match_method=SponsorMatchMethod.NO_MATCH,
            recognised_sponsor=False, possible_match=False, human_review_required=False,
            note=note or "Rejected by admin: not a genuine sponsor match.",
        )
    else:
        raise SponsorReviewError(f"decision must be 'confirm' or 'reject', got {decision!r}")

    conn.execute(
        text("update vacancy set sponsorship_signal = cast(:signal as jsonb) where vacancy_id = :id"),
        {"signal": json.dumps(signal.model_dump(mode="json"), default=str), "id": str(vacancy_id)},
    )
    return signal.model_dump(mode="json")


# --- 3. Extraction spot-check view (read-only) ---------------------------

EXTRACTION_REVIEW_NOTE = (
    "Read-only spot-check view. extract-cv/extract-description never persist "
    "their draft (see their own docstrings), so there is no stored original to "
    "diff a confirmed submission against -- whether it was edited before "
    "confirming cannot be reconstructed from existing data. Only the confirmed "
    "value itself is shown here, for a human to judge directly."
)


def list_extraction_review(conn: Connection, *, limit: int = 50) -> Dict[str, Any]:
    candidate_rows = conn.execute(
        text(
            """
            select v.talent_id, t.full_name, v.element_id, v.value, v.value_status, v.created_at
            from talent_element_value v
            join talent t on t.talent_id = v.talent_id
            where v.source_type = 'ai_extraction'
            order by v.created_at desc
            limit :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    vacancy_rows = conn.execute(
        text(
            """
            select v.vacancy_id, va.role_title, va.company_name, v.element_id, v.value, v.value_status, v.created_at
            from vacancy_element_value v
            join vacancy va on va.vacancy_id = v.vacancy_id
            where v.source_type = 'ai_extraction'
            order by v.created_at desc
            limit :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    return {
        "note": EXTRACTION_REVIEW_NOTE,
        "candidate_submissions": [
            {
                "talent_id": str(r["talent_id"]), "full_name": r["full_name"], "element_id": r["element_id"],
                "value": _as_json(r["value"]), "value_status": r["value_status"], "created_at": r["created_at"].isoformat(),
            }
            for r in candidate_rows
        ],
        "vacancy_submissions": [
            {
                "vacancy_id": str(r["vacancy_id"]), "title": r["role_title"], "company_name": r["company_name"],
                "element_id": r["element_id"], "value": _as_json(r["value"]), "value_status": r["value_status"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in vacancy_rows
        ],
    }
