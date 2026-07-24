"""Confirms api.ingestion_store.insert_vacancy_dedup_review actually persists
a queryable row -- not just that IngestionOutcome exposes confidence/snapshot_id
(see tests/test_company_then_scraped_dedup_merge.py for that, DB-free, check).

Runs against the real API + Neon (this project's configured dev DB), since
that's the only way to prove a row lands and is queryable. No Claude API
call is involved, so no ANTHROPIC_API_KEY is needed here.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from canonical_vacancy import DEFAULT_PUBLIC_WEIGHTS  # noqa: E402
from company_intake import canonicalise_company_submission  # noqa: E402
from source_schemas import SourceSnapshot, SourceTrustLevel  # noqa: E402

from api.database import engine  # noqa: E402
from api.ingestion_store import insert_snapshot_if_new, insert_vacancy_dedup_review  # noqa: E402
from api.vacancy_store import insert_vacancy  # noqa: E402


def test_insert_vacancy_dedup_review_persists_a_queryable_row():
    profile = canonicalise_company_submission(
        {
            "company_name": "Dedup Review Test BV", "title": "Test Role",
            "description_text": "Exists only to anchor a vacancy_dedup_review row in this test.",
        },
        company_id=None, category_weights=DEFAULT_PUBLIC_WEIGHTS,
    )
    snapshot = SourceSnapshot(
        snapshot_id=f"snap-test-{uuid.uuid4().hex[:16]}", source_record_id="test-source-record",
        source_id="greenhouse_public_api", source_url="https://example.com/jobs/test",
        retrieved_at=datetime.now(timezone.utc), content_hash=uuid.uuid4().hex,
        raw_payload={"test": True}, trust_level=SourceTrustLevel.OFFICIAL_ATS,
    )

    try:
        with engine.begin() as conn:
            insert_vacancy(conn, profile)
            insert_snapshot_if_new(conn, snapshot)
            insert_vacancy_dedup_review(
                conn, incoming_snapshot_id=snapshot.snapshot_id, candidate_vacancy_id=profile.vacancy_id,
                decision_reason="Plausible same-company vacancy match but similarity is not decisive",
                confidence=0.87,
            )

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "select incoming_snapshot_id, candidate_vacancy_id, decision_reason, confidence, status "
                    "from vacancy_dedup_review where candidate_vacancy_id = :id"
                ),
                {"id": profile.vacancy_id},
            ).mappings().first()

        assert row is not None
        assert row["incoming_snapshot_id"] == snapshot.snapshot_id
        assert str(row["candidate_vacancy_id"]) == profile.vacancy_id
        assert row["decision_reason"] == "Plausible same-company vacancy match but similarity is not decisive"
        assert float(row["confidence"]) == 0.87
        assert row["status"] == "pending"
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from vacancy_dedup_review where candidate_vacancy_id = :id"), {"id": profile.vacancy_id})
            conn.execute(text("delete from source_snapshot where snapshot_id = :id"), {"id": snapshot.snapshot_id})
            conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": profile.vacancy_id})


def test_insert_vacancy_dedup_review_is_idempotent_on_repeated_polling():
    """Re-polling unchanged content re-derives the same (incoming_snapshot_id,
    candidate_vacancy_id) pair every cycle (snapshot_id is a content-hash
    fingerprint of unchanged source content). Confirms the same pair does not
    accumulate a fresh row every time it's re-detected -- caught for real
    against live Neon data: a second live poll cycle doubled 6 rows to 12
    before this fix (unique index + ON CONFLICT DO NOTHING)."""
    profile = canonicalise_company_submission(
        {
            "company_name": "Dedup Review Idempotency Test BV", "title": "Test Role",
            "description_text": "Exists only to anchor a repeated vacancy_dedup_review insert in this test.",
        },
        company_id=None, category_weights=DEFAULT_PUBLIC_WEIGHTS,
    )
    snapshot = SourceSnapshot(
        snapshot_id=f"snap-test-{uuid.uuid4().hex[:16]}", source_record_id="test-source-record",
        source_id="greenhouse_public_api", source_url="https://example.com/jobs/test",
        retrieved_at=datetime.now(timezone.utc), content_hash=uuid.uuid4().hex,
        raw_payload={"test": True}, trust_level=SourceTrustLevel.OFFICIAL_ATS,
    )

    try:
        with engine.begin() as conn:
            insert_vacancy(conn, profile)
            insert_snapshot_if_new(conn, snapshot)

        # Simulates the same ambiguity being re-detected on three separate
        # poll cycles -- exactly what happened for real on live Greenhouse data.
        for _ in range(3):
            with engine.begin() as conn:
                insert_vacancy_dedup_review(
                    conn, incoming_snapshot_id=snapshot.snapshot_id, candidate_vacancy_id=profile.vacancy_id,
                    decision_reason="Plausible same-company vacancy match but similarity is not decisive",
                    confidence=0.87,
                )

        with engine.connect() as conn:
            n = conn.execute(
                text("select count(*) from vacancy_dedup_review where candidate_vacancy_id = :id"),
                {"id": profile.vacancy_id},
            ).scalar_one()

        assert n == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from vacancy_dedup_review where candidate_vacancy_id = :id"), {"id": profile.vacancy_id})
            conn.execute(text("delete from source_snapshot where snapshot_id = :id"), {"id": snapshot.snapshot_id})
            conn.execute(text("delete from vacancy where vacancy_id = :id"), {"id": profile.vacancy_id})
