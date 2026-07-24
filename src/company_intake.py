from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict

from canonical_vacancy import canonicalise_raw_vacancy
from schemas import Category
from source_schemas import (
    AcquisitionMethod, CanonicalVacancyProfile, RawVacancyRecord, SourceTrustLevel,
    VacancyIntakeSource, VerificationStatus, WeightingMode,
)


def raw_from_company_submission(submission: Dict[str, Any], *, source_record_id: str = "company-form") -> RawVacancyRecord:
    return RawVacancyRecord(
        source_id="company_direct_form",
        source_record_id=source_record_id,
        intake_source=VacancyIntakeSource.COMPANY_DIRECT,
        acquisition_method=AcquisitionMethod.FORM,
        source_url=submission.get("source_url") or "shexon://company-intake",
        external_job_id=submission.get("external_job_id"),
        company_name=submission["company_name"],
        company_domain=submission.get("company_domain"),
        title=submission["title"],
        description_text=submission["description_text"],
        location_text=submission.get("location_text"),
        department=submission.get("department"),
        employment_types=submission.get("employment_types", []),
        work_mode=submission.get("work_mode"),
        apply_url=submission.get("apply_url"),
        date_posted=submission.get("date_posted"),
        valid_through=submission.get("valid_through"),
        salary=submission.get("salary"),
        raw_payload=submission,
        trust_level=SourceTrustLevel.COMPANY_CONFIRMED,
        retrieved_at=datetime.now(timezone.utc),
    )


def canonicalise_company_submission(
    submission: Dict[str, Any],
    *, company_id: str,
    category_weights: Dict[Category, float],
) -> CanonicalVacancyProfile:
    raw = raw_from_company_submission(submission)
    return canonicalise_raw_vacancy(
        raw,
        company_id=company_id,
        company_domain=submission.get("company_domain"),
        category_weights=category_weights,
        weighting_mode=WeightingMode.COMPANY_CONFIRMED,
        verification_status=VerificationStatus.COMPANY_VALIDATED,
    )
