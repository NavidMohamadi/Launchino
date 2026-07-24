"""Persists CanonicalVacancyProfile (src/source_schemas.py) into the `vacancy` table.

CanonicalVacancyProfile is denormalised across several tables in
src/database_schema.sql. Only the fields that live directly on `vacancy`
are round-tripped in profile_to_row/row_to_profile:

- element_values are stored in vacancy_element_value (populated by
  api/routers/vacancies.py's workshop endpoint) and reloaded fresh on every
  fetch_vacancy() call via load_element_values(), so a GET reflects
  whatever has actually been submitted, including from an earlier request.
- provenance / source_conflicts live in vacancy_field_provenance /
  vacancy_source_conflict, populated by the full ingestion pipeline
  (src/vacancy_ingestion.py), which this direct-submission endpoint does not
  run. They are always reconstructed as empty lists here.
- source_snapshot_ids reference rows in source_snapshot, which a direct
  company submission does not create; the synthetic ID CanonicalVacancyProfile
  generates internally is not persisted or reconstructed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from schemas import Category, VacancyElementValue
from source_schemas import CanonicalVacancyProfile, CompanySponsorshipSignal


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def profile_to_row(profile: CanonicalVacancyProfile) -> Dict[str, Any]:
    return {
        "vacancy_id": profile.vacancy_id,
        "company_id": profile.company_id,
        "company_name": profile.company_name,
        "company_domain": profile.company_domain,
        "role_title": profile.title,
        "description_text": profile.description_text,
        "primary_source_url": profile.primary_source_url,
        "apply_url": profile.apply_url,
        "external_job_ids": json.dumps(profile.external_job_ids),
        "intake_sources": json.dumps([s.value for s in profile.intake_sources]),
        "acquisition_methods": json.dumps([m.value for m in profile.acquisition_methods]),
        "verification_status": profile.verification_status.value,
        "lifecycle_status": profile.lifecycle_status.value,
        "weighting_mode": profile.weighting_mode.value,
        "weights_confirmed_by_company": profile.weights_confirmed_by_company,
        "category_weights": json.dumps({c.value: w for c, w in profile.category_weights.items()}),
        "canonical_key": profile.canonical_key,
        "content_hash": profile.content_hash,
        "location_text": profile.location_text,
        "department": profile.department,
        "employment_types": json.dumps(profile.employment_types),
        "work_mode": profile.work_mode,
        "date_posted": profile.date_posted,
        "valid_through": profile.valid_through,
        "salary": json.dumps(profile.salary) if profile.salary is not None else None,
        "sponsorship_signal": (
            json.dumps(profile.sponsorship_signal.model_dump(mode="json"))
            if profile.sponsorship_signal is not None else None
        ),
        "first_seen_at": profile.first_seen_at,
        "last_seen_at": profile.last_seen_at,
        "last_material_change_at": profile.last_material_change_at,
        "missing_poll_count": profile.missing_poll_count,
        "closed_reason": profile.closed_reason,
        "closed_at": profile.closed_at,
        "reopened_at": profile.reopened_at,
        "reopened_reason": profile.reopened_reason,
        "record_version": profile.version,
    }


def _row_to_element_value(row: Mapping[str, Any]) -> VacancyElementValue:
    row = dict(row)
    return VacancyElementValue(
        vacancy_id=str(row["vacancy_id"]),
        element_id=row["element_id"],
        value=_as_json(row["value"]),
        value_status=row["value_status"],
        unknown_reason=row["unknown_reason"],
        not_scored_reason=row["not_scored_reason"],
        source_type=row["source_type"],
        item_importance=row["item_importance"],
        requirement_type=row["requirement_type"],
        trainability_window=row["trainability_window"],
        last_confirmed_at=row["last_confirmed_at"],
    )


def load_element_values(conn: Connection, vacancy_id: UUID) -> List[VacancyElementValue]:
    rows = conn.execute(
        text(
            """
            select vacancy_id, element_id, value, value_status, unknown_reason, not_scored_reason,
                   source_type, item_importance, requirement_type, trainability_window, last_confirmed_at
            from vacancy_element_value
            where vacancy_id = :vacancy_id
            """
        ),
        {"vacancy_id": str(vacancy_id)},
    ).mappings().all()
    return [_row_to_element_value(r) for r in rows]


def row_to_profile(
    row: Mapping[str, Any], *, element_values: Optional[List[VacancyElementValue]] = None,
) -> CanonicalVacancyProfile:
    row = dict(row)
    sponsorship_signal = _as_json(row["sponsorship_signal"])
    return CanonicalVacancyProfile(
        vacancy_id=str(row["vacancy_id"]),
        company_id=str(row["company_id"]) if row["company_id"] else None,
        company_name=row["company_name"],
        company_domain=row["company_domain"],
        title=row["role_title"],
        description_text=row["description_text"],
        external_job_ids=_as_json(row["external_job_ids"]),
        primary_source_url=row["primary_source_url"],
        apply_url=row["apply_url"],
        intake_sources=_as_json(row["intake_sources"]),
        acquisition_methods=_as_json(row["acquisition_methods"]),
        verification_status=row["verification_status"],
        lifecycle_status=row["lifecycle_status"],
        weighting_mode=row["weighting_mode"],
        weights_confirmed_by_company=row["weights_confirmed_by_company"],
        category_weights={Category(k): v for k, v in _as_json(row["category_weights"]).items()},
        location_text=row["location_text"],
        department=row["department"],
        employment_types=_as_json(row["employment_types"]),
        work_mode=row["work_mode"],
        date_posted=row["date_posted"],
        valid_through=row["valid_through"],
        salary=_as_json(row["salary"]),
        element_values=element_values or [],
        provenance=[],
        source_conflicts=[],
        sponsorship_signal=CompanySponsorshipSignal.model_validate(sponsorship_signal) if sponsorship_signal else None,
        source_snapshot_ids=[],
        canonical_key=row["canonical_key"],
        content_hash=row["content_hash"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        last_material_change_at=row["last_material_change_at"],
        missing_poll_count=row["missing_poll_count"],
        closed_reason=row["closed_reason"],
        closed_at=row["closed_at"],
        reopened_at=row["reopened_at"],
        reopened_reason=row["reopened_reason"],
        version=row["record_version"],
    )


def insert_vacancy(conn: Connection, profile: CanonicalVacancyProfile) -> None:
    row = profile_to_row(profile)
    conn.execute(
        text(
            """
            insert into vacancy (
                vacancy_id, company_id, company_name, company_domain, role_title,
                description_text, primary_source_url, apply_url, external_job_ids,
                intake_sources, acquisition_methods, verification_status, lifecycle_status,
                weighting_mode, weights_confirmed_by_company, category_weights, canonical_key,
                content_hash, location_text, department, employment_types, work_mode,
                date_posted, valid_through, salary, sponsorship_signal, first_seen_at,
                last_seen_at, last_material_change_at, missing_poll_count, closed_reason,
                closed_at, reopened_at, reopened_reason, record_version
            ) values (
                :vacancy_id, :company_id, :company_name, :company_domain, :role_title,
                :description_text, :primary_source_url, :apply_url, cast(:external_job_ids as jsonb),
                cast(:intake_sources as jsonb), cast(:acquisition_methods as jsonb), :verification_status,
                :lifecycle_status, :weighting_mode, :weights_confirmed_by_company,
                cast(:category_weights as jsonb), :canonical_key, :content_hash, :location_text,
                :department, cast(:employment_types as jsonb), :work_mode, :date_posted,
                :valid_through, cast(:salary as jsonb), cast(:sponsorship_signal as jsonb),
                :first_seen_at, :last_seen_at, :last_material_change_at, :missing_poll_count,
                :closed_reason, :closed_at, :reopened_at, :reopened_reason, :record_version
            )
            """
        ),
        row,
    )


def upsert_vacancy(conn: Connection, profile: CanonicalVacancyProfile) -> None:
    """Like insert_vacancy, but updates an existing row instead of failing on
    conflict -- for the ingestion pipeline (api/job_discovery_scheduler.py),
    where the same real vacancy_id can legitimately be re-persisted across
    repeated poll cycles as vacancy_dedup/vacancy_merge revise its content."""
    row = profile_to_row(profile)
    conn.execute(
        text(
            """
            insert into vacancy (
                vacancy_id, company_id, company_name, company_domain, role_title,
                description_text, primary_source_url, apply_url, external_job_ids,
                intake_sources, acquisition_methods, verification_status, lifecycle_status,
                weighting_mode, weights_confirmed_by_company, category_weights, canonical_key,
                content_hash, location_text, department, employment_types, work_mode,
                date_posted, valid_through, salary, sponsorship_signal, first_seen_at,
                last_seen_at, last_material_change_at, missing_poll_count, closed_reason,
                closed_at, reopened_at, reopened_reason, record_version
            ) values (
                :vacancy_id, :company_id, :company_name, :company_domain, :role_title,
                :description_text, :primary_source_url, :apply_url, cast(:external_job_ids as jsonb),
                cast(:intake_sources as jsonb), cast(:acquisition_methods as jsonb), :verification_status,
                :lifecycle_status, :weighting_mode, :weights_confirmed_by_company,
                cast(:category_weights as jsonb), :canonical_key, :content_hash, :location_text,
                :department, cast(:employment_types as jsonb), :work_mode, :date_posted,
                :valid_through, cast(:salary as jsonb), cast(:sponsorship_signal as jsonb),
                :first_seen_at, :last_seen_at, :last_material_change_at, :missing_poll_count,
                :closed_reason, :closed_at, :reopened_at, :reopened_reason, :record_version
            )
            on conflict (vacancy_id) do update set
                company_id = excluded.company_id, company_name = excluded.company_name,
                company_domain = excluded.company_domain, role_title = excluded.role_title,
                description_text = excluded.description_text, primary_source_url = excluded.primary_source_url,
                apply_url = excluded.apply_url, external_job_ids = excluded.external_job_ids,
                intake_sources = excluded.intake_sources, acquisition_methods = excluded.acquisition_methods,
                verification_status = excluded.verification_status, lifecycle_status = excluded.lifecycle_status,
                weighting_mode = excluded.weighting_mode,
                weights_confirmed_by_company = excluded.weights_confirmed_by_company,
                category_weights = excluded.category_weights, canonical_key = excluded.canonical_key,
                content_hash = excluded.content_hash, location_text = excluded.location_text,
                department = excluded.department, employment_types = excluded.employment_types,
                work_mode = excluded.work_mode, date_posted = excluded.date_posted,
                valid_through = excluded.valid_through, salary = excluded.salary,
                sponsorship_signal = excluded.sponsorship_signal, last_seen_at = excluded.last_seen_at,
                last_material_change_at = excluded.last_material_change_at,
                missing_poll_count = excluded.missing_poll_count, closed_reason = excluded.closed_reason,
                closed_at = excluded.closed_at, reopened_at = excluded.reopened_at,
                reopened_reason = excluded.reopened_reason, record_version = excluded.record_version,
                updated_at = now()
            """
        ),
        row,
    )


def fetch_vacancy(conn: Connection, vacancy_id: UUID) -> Optional[CanonicalVacancyProfile]:
    row = conn.execute(
        text("select * from vacancy where vacancy_id = :vacancy_id"), {"vacancy_id": str(vacancy_id)}
    ).mappings().first()
    if not row:
        return None
    element_values = load_element_values(conn, vacancy_id)
    return row_to_profile(row, element_values=element_values)


def company_exists(conn: Connection, company_id: UUID) -> bool:
    row = conn.execute(
        text("select 1 from company where company_id = :company_id"), {"company_id": str(company_id)}
    ).first()
    return row is not None
