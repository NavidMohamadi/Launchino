from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas import VacancyElementValue
from source_schemas import CanonicalVacancyProfile, VacancyFieldProvenance, VerificationStatus


class ExtractedVacancyElement(BaseModel):
    value: VacancyElementValue
    source_quote: str
    source_url: str
    extraction_confidence: float = Field(ge=0, le=1)
    source_snapshot_id: str


class VacancyExtractionResult(BaseModel):
    extracted_elements: List[ExtractedVacancyElement] = Field(default_factory=list)
    unanswered_element_ids: List[str] = Field(default_factory=list)
    review_flags: List[str] = Field(default_factory=list)


def apply_extraction_result(
    profile: CanonicalVacancyProfile,
    result: VacancyExtractionResult,
    *, verification_status: VerificationStatus = VerificationStatus.AUTO_EXTRACTED,
) -> CanonicalVacancyProfile:
    updated = profile.model_copy(deep=True)
    by_id = {row.element_id: row for row in updated.element_values}
    for extracted in result.extracted_elements:
        by_id[extracted.value.element_id] = extracted.value
        updated.provenance.append(VacancyFieldProvenance(
            field_path=f"element_values.{extracted.value.element_id}",
            source_snapshot_id=extracted.source_snapshot_id,
            source_url=extracted.source_url,
            extracted_at=datetime.now(timezone.utc),
            extraction_confidence=extracted.extraction_confidence,
            verification_status=verification_status,
            source_trust_level=max((p.source_trust_level for p in profile.provenance), default=1),
            note=f"Source quote: {extracted.source_quote[:300]}",
        ))
    updated.element_values = list(by_id.values())
    return updated
