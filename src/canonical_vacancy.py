from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from schemas import Category
from source_schemas import (
    CanonicalVacancyProfile, RawVacancyRecord, VerificationStatus, VacancyFieldProvenance,
    VacancyLifecycleStatus, WeightingMode,
)
from vacancy_utils import canonical_job_key, normalise_domain, stable_hash


# Equal weighting across the 5 categories with real seeded elements today
# (PRACT/TEAM/CAREER/MOT/ENV). CAP/TASK stay at 0 -- the Fit Dictionary has zero
# seeded elements for either (see PROJECT_NOTES.md); a nonzero weight here would
# either be silently renormalized away (pre-fix behavior) or now correctly
# trigger a "no data available for this category" clarification flag -- neither
# of which is useful when it can just be 0 instead. Keep this in exact sync with
# frontend/src/pages/VacancyWorkshopPage.jsx's DEFAULT_CATEGORY_WEIGHTS -- there
# is no runtime single-sourcing between the two (see PROJECT_NOTES.md).
DEFAULT_PUBLIC_WEIGHTS = {
    Category.PRACT: 20.0,
    Category.CAP: 0.0,
    Category.TASK: 0.0,
    Category.TEAM: 20.0,
    Category.CAREER: 20.0,
    Category.MOT: 20.0,
    Category.ENV: 20.0,
}


def canonicalise_raw_vacancy(
    raw: RawVacancyRecord,
    *, company_id: str | None = None,
    company_domain: str | None = None,
    vacancy_id: str | None = None,
    category_weights: dict[Category, float] | None = None,
    weighting_mode: WeightingMode = WeightingMode.BALANCED_DEFAULT,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
    snapshot_id: str | None = None,
) -> CanonicalVacancyProfile:
    now = raw.retrieved_at or datetime.now(timezone.utc)
    description = raw.description_text or ""
    domain = normalise_domain(company_domain or raw.company_domain) or None
    snapshot_id = snapshot_id or f"snap-{stable_hash(raw.raw_payload or raw.model_dump(mode='json'))[:16]}"
    canonical_key = canonical_job_key(
        company_domain=domain,
        company_name=raw.company_name,
        title=raw.title,
        location=raw.location_text,
    )
    provenance = []
    for field_path, value in {
        "title": raw.title,
        "description_text": description,
        "location_text": raw.location_text,
        "department": raw.department,
        "employment_types": raw.employment_types,
        "work_mode": raw.work_mode,
        "apply_url": raw.apply_url,
        "date_posted": raw.date_posted,
        "valid_through": raw.valid_through,
    }.items():
        if value not in (None, "", [], {}):
            provenance.append(VacancyFieldProvenance(
                field_path=field_path,
                source_snapshot_id=snapshot_id,
                source_url=raw.source_url,
                extraction_confidence=1.0 if raw.acquisition_method.value in {"api", "json_ld"} else 0.75,
                verification_status=verification_status,
                source_trust_level=raw.trust_level,
            ))
    return CanonicalVacancyProfile(
        vacancy_id=vacancy_id or str(uuid4()),
        company_id=company_id,
        company_name=raw.company_name,
        company_domain=domain,
        title=raw.title,
        description_text=description,
        external_job_ids={raw.source_id: raw.external_job_id} if raw.external_job_id else {},
        primary_source_url=raw.source_url,
        apply_url=raw.apply_url,
        intake_sources=[raw.intake_source],
        acquisition_methods=[raw.acquisition_method],
        verification_status=verification_status,
        lifecycle_status=VacancyLifecycleStatus.ACTIVE,
        weighting_mode=weighting_mode,
        weights_confirmed_by_company=weighting_mode == WeightingMode.COMPANY_CONFIRMED,
        category_weights=category_weights or DEFAULT_PUBLIC_WEIGHTS,
        location_text=raw.location_text,
        department=raw.department,
        employment_types=raw.employment_types,
        work_mode=raw.work_mode,
        date_posted=raw.date_posted,
        valid_through=raw.valid_through,
        salary=raw.salary,
        provenance=provenance,
        source_snapshot_ids=[snapshot_id],
        canonical_key=canonical_key,
        content_hash=stable_hash({"title": raw.title, "description": description, "location": raw.location_text}),
        first_seen_at=now,
        last_seen_at=now,
        last_material_change_at=now,
    )
