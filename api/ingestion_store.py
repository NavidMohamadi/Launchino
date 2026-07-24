"""Persistence for the real ingestion pipeline (api/job_discovery_scheduler.py).

Covers the tables api/vacancy_store.py doesn't: source_policy (must be seeded
before any company_job_source row can reference it -- see seed_source_policy),
company, company_job_source, source_snapshot, vacancy_source_link,
vacancy_field_provenance, vacancy_source_conflict, and vacancy_dedup_review.
Everything here is a straight round-trip of the existing src/source_schemas.py
models; no new scoring or comparator logic.

insert_vacancy_dedup_review relies on src/source_schemas.py's IngestionOutcome
exposing confidence/snapshot_id (added for exactly this purpose -- see
PROJECT_NOTES.md); the underlying dedup decision in src/vacancy_dedup.py is
untouched. Caller (api/job_discovery_scheduler.py) must insert the referenced
source_snapshot and vacancy rows first -- both are foreign keys here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from source_policy import SourcePolicyRegistry
from source_schemas import (
    CanonicalVacancyProfile, CompanyJobSource, CompanyRecord, SourceConflict,
    SourcePolicy, SourceSnapshot, VacancyFieldProvenance,
)

from api import REPO_ROOT
from api.vacancy_store import row_to_profile

SOURCE_REGISTRY_PATH = REPO_ROOT / "data" / "source_registry.json"


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def seed_source_policy(conn: Connection, path: Path = SOURCE_REGISTRY_PATH) -> int:
    """company_job_source.source_id has a foreign key to source_policy; this
    must run before upsert_company_job_source or that insert fails closed."""
    policies = SourcePolicyRegistry.from_json(path).policies
    for policy in policies.values():
        conn.execute(
            text(
                """
                insert into source_policy (
                    source_id, display_name, enabled, terms_review_status, allowed_methods,
                    robots_policy, max_requests_per_minute, partner_approval_required, notes
                ) values (
                    :source_id, :display_name, :enabled, :terms_review_status, cast(:allowed_methods as jsonb),
                    :robots_policy, :max_requests_per_minute, :partner_approval_required, :notes
                )
                on conflict (source_id) do update set
                    display_name = excluded.display_name, enabled = excluded.enabled,
                    terms_review_status = excluded.terms_review_status, allowed_methods = excluded.allowed_methods,
                    robots_policy = excluded.robots_policy, max_requests_per_minute = excluded.max_requests_per_minute,
                    partner_approval_required = excluded.partner_approval_required, notes = excluded.notes,
                    updated_at = now()
                """
            ),
            {
                "source_id": policy.source_id,
                "display_name": policy.display_name,
                "enabled": policy.enabled,
                "terms_review_status": policy.terms_review_status.value,
                "allowed_methods": json.dumps([m.value for m in policy.allowed_methods]),
                "robots_policy": policy.robots_policy.value,
                "max_requests_per_minute": policy.max_requests_per_minute,
                "partner_approval_required": policy.partner_approval_required,
                "notes": policy.notes,
            },
        )
    return len(policies)


def upsert_company(conn: Connection, company: CompanyRecord) -> None:
    conn.execute(
        text(
            """
            insert into company (
                company_id, legal_name, display_name, website_domain, career_page_url,
                country_code, kvk_number, active
            ) values (
                :company_id, :legal_name, :display_name, :website_domain, :career_page_url,
                :country_code, :kvk_number, :active
            )
            on conflict (company_id) do update set
                legal_name = excluded.legal_name, display_name = excluded.display_name,
                website_domain = excluded.website_domain, career_page_url = excluded.career_page_url,
                country_code = excluded.country_code, kvk_number = excluded.kvk_number,
                active = excluded.active, updated_at = now()
            """
        ),
        {
            "company_id": company.company_id,
            "legal_name": company.legal_name,
            "display_name": company.display_name,
            "website_domain": company.website_domain,
            "career_page_url": company.career_page_url,
            "country_code": company.country,
            "kvk_number": company.kvk_number,
            "active": company.active,
        },
    )


def upsert_company_job_source(conn: Connection, source: CompanyJobSource) -> None:
    conn.execute(
        text(
            """
            insert into company_job_source (
                source_record_id, company_id, source_id, intake_source, acquisition_method,
                board_identifier, listing_url, enabled, polling_interval_minutes,
                last_polled_at, next_poll_at
            ) values (
                :source_record_id, :company_id, :source_id, :intake_source, :acquisition_method,
                :board_identifier, :listing_url, :enabled, :polling_interval_minutes,
                :last_polled_at, :next_poll_at
            )
            on conflict (source_record_id) do update set
                company_id = excluded.company_id, source_id = excluded.source_id,
                intake_source = excluded.intake_source, acquisition_method = excluded.acquisition_method,
                board_identifier = excluded.board_identifier, listing_url = excluded.listing_url,
                enabled = excluded.enabled, polling_interval_minutes = excluded.polling_interval_minutes,
                last_polled_at = excluded.last_polled_at, next_poll_at = excluded.next_poll_at
            """
        ),
        {
            "source_record_id": source.source_record_id,
            "company_id": source.company_id,
            "source_id": source.source_id,
            "intake_source": source.intake_source.value,
            "acquisition_method": source.acquisition_method.value,
            "board_identifier": source.board_identifier,
            "listing_url": source.listing_url,
            "enabled": source.enabled,
            "polling_interval_minutes": source.polling_interval_minutes,
            "last_polled_at": source.last_polled_at,
            "next_poll_at": source.next_poll_at,
        },
    )


def insert_snapshot_if_new(conn: Connection, snapshot: SourceSnapshot) -> None:
    conn.execute(
        text(
            """
            insert into source_snapshot (
                snapshot_id, source_record_id, source_id, source_url, external_job_id,
                retrieved_at, http_status, content_type, content_hash, raw_payload, trust_level
            ) values (
                :snapshot_id, :source_record_id, :source_id, :source_url, :external_job_id,
                :retrieved_at, :http_status, :content_type, :content_hash, cast(:raw_payload as jsonb),
                :trust_level
            )
            on conflict (snapshot_id) do nothing
            """
        ),
        {
            "snapshot_id": snapshot.snapshot_id,
            "source_record_id": snapshot.source_record_id,
            "source_id": snapshot.source_id,
            "source_url": snapshot.source_url,
            "external_job_id": snapshot.external_job_id,
            "retrieved_at": snapshot.retrieved_at,
            "http_status": snapshot.http_status,
            "content_type": snapshot.content_type,
            "content_hash": snapshot.content_hash,
            "raw_payload": json.dumps(snapshot.raw_payload),
            "trust_level": int(snapshot.trust_level),
        },
    )


def link_vacancy_snapshot(conn: Connection, *, vacancy_id: str, snapshot_id: str, is_primary: bool) -> None:
    conn.execute(
        text(
            """
            insert into vacancy_source_link (vacancy_id, snapshot_id, is_primary)
            values (:vacancy_id, :snapshot_id, :is_primary)
            on conflict (vacancy_id, snapshot_id) do update set is_primary = excluded.is_primary
            """
        ),
        {"vacancy_id": vacancy_id, "snapshot_id": snapshot_id, "is_primary": is_primary},
    )


def insert_provenance(conn: Connection, *, vacancy_id: str, provenance: VacancyFieldProvenance) -> None:
    conn.execute(
        text(
            """
            insert into vacancy_field_provenance (
                vacancy_id, field_path, snapshot_id, source_url, extracted_at,
                extraction_confidence, verification_status, source_trust_level, note
            ) values (
                :vacancy_id, :field_path, :snapshot_id, :source_url, :extracted_at,
                :extraction_confidence, :verification_status, :source_trust_level, :note
            )
            """
        ),
        {
            "vacancy_id": vacancy_id,
            "field_path": provenance.field_path,
            "snapshot_id": provenance.source_snapshot_id,
            "source_url": provenance.source_url,
            "extracted_at": provenance.extracted_at,
            "extraction_confidence": provenance.extraction_confidence,
            "verification_status": provenance.verification_status.value,
            "source_trust_level": int(provenance.source_trust_level),
            "note": provenance.note,
        },
    )


def insert_source_conflict(conn: Connection, *, vacancy_id: str, conflict: SourceConflict) -> None:
    conn.execute(
        text(
            """
            insert into vacancy_source_conflict (
                vacancy_id, field_path, values_by_snapshot, resolution_status,
                resolved_value, resolved_by, resolution_note
            ) values (
                :vacancy_id, :field_path, cast(:values_by_snapshot as jsonb), :resolution_status,
                cast(:resolved_value as jsonb), :resolved_by, :resolution_note
            )
            """
        ),
        {
            "vacancy_id": vacancy_id,
            "field_path": conflict.field_path,
            "values_by_snapshot": json.dumps(conflict.values_by_snapshot, default=str),
            "resolution_status": conflict.resolution_status,
            "resolved_value": json.dumps(conflict.resolved_value, default=str) if conflict.resolved_value is not None else None,
            "resolved_by": conflict.resolved_by,
            "resolution_note": conflict.resolution_note,
        },
    )


def insert_vacancy_dedup_review(
    conn: Connection, *, incoming_snapshot_id: str, candidate_vacancy_id: str,
    decision_reason: str, confidence: Optional[float],
) -> None:
    """Persist a review_required dedup outcome as a queryable, actionable row.

    incoming_snapshot_id and candidate_vacancy_id are foreign keys to
    source_snapshot and vacancy respectively -- the caller must have already
    persisted both (api/job_discovery_scheduler.py does this by running
    snapshot and vacancy upserts before calling this).

    Re-polling unchanged content re-derives the same (incoming_snapshot_id,
    candidate_vacancy_id) pair every cycle (snapshot_id is a content-hash
    fingerprint), so this is idempotent on that pair via the unique index in
    src/database_schema.sql -- an already-recorded review (pending or
    already actioned) is left alone rather than getting a fresh duplicate
    row every poll interval."""
    conn.execute(
        text(
            """
            insert into vacancy_dedup_review (
                review_id, incoming_snapshot_id, candidate_vacancy_id, decision_reason,
                confidence, status
            ) values (
                gen_random_uuid(), :incoming_snapshot_id, :candidate_vacancy_id, :decision_reason,
                :confidence, 'pending'
            )
            on conflict (incoming_snapshot_id, candidate_vacancy_id) do nothing
            """
        ),
        {
            "incoming_snapshot_id": incoming_snapshot_id,
            "candidate_vacancy_id": candidate_vacancy_id,
            "decision_reason": decision_reason,
            "confidence": confidence,
        },
    )


def insert_poll_run(
    conn: Connection, *, source_record_id: str, started_at, completed_at, status: str,
    jobs_seen: int, jobs_created: int, jobs_updated: int, error_message: Optional[str],
) -> None:
    """Persist one poll_run row per source per cycle -- the table existed in
    the schema from the start but nothing ever wrote to it (see
    PROJECT_NOTES.md); api/job_discovery_scheduler.py's run_poll_cycle already
    computes exactly this data (BoardValidationResult.status/job_count/error)
    per source, it just discarded it after printing. This is a pure add: no
    existing behavior changes, one insert per due source at the end of the
    cycle."""
    conn.execute(
        text(
            """
            insert into poll_run (
                poll_run_id, source_record_id, started_at, completed_at, status,
                jobs_seen, jobs_created, jobs_updated, error_message
            ) values (
                gen_random_uuid(), :source_record_id, :started_at, :completed_at, :status,
                :jobs_seen, :jobs_created, :jobs_updated, :error_message
            )
            """
        ),
        {
            "source_record_id": source_record_id, "started_at": started_at, "completed_at": completed_at,
            "status": status, "jobs_seen": jobs_seen, "jobs_created": jobs_created,
            "jobs_updated": jobs_updated, "error_message": error_message,
        },
    )


def load_existing_profiles(conn: Connection) -> List[CanonicalVacancyProfile]:
    """Bootstrap a VacancyRepository with what's already in Postgres, so a
    repeated poll cycle can dedup against vacancies a previous run created --
    not just against what this single process run has seen so far."""
    rows = conn.execute(text("select * from vacancy")).mappings().all()
    return [row_to_profile(row) for row in rows]
