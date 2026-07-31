from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from schemas import TalentElementValue


class ExtractedTalentElement(BaseModel):
    value: TalentElementValue
    source_quote: str
    extraction_confidence: float = Field(ge=0, le=1)


class ExtractedBasicInfo(BaseModel):
    """phone only -- a plain talent column, not a Fit Dictionary element
    (see PROJECT_NOTES.md's Phase 1 entry), so it doesn't fit
    ExtractedTalentElement/TalentElementValue's shape. contact_preference is
    deliberately NOT extractable here: a CV would essentially never state how
    someone wants to be contacted, and guessing it would violate this whole
    prompt's "extract only explicit information" rule -- it stays
    manual-entry-only via PATCH /candidates/{id}/basic-info, defaulting to
    'email' until the candidate sets it themselves.
    """

    phone: Optional[str] = None
    evidence_quote: Optional[str] = None


class CandidateExtractionResult(BaseModel):
    extracted_elements: List[ExtractedTalentElement] = Field(default_factory=list)
    basic_info: Optional[ExtractedBasicInfo] = None
    # A real skill/tool/task the CV supports but that has no match in the Fit
    # Dictionary sent to the model (e.g. because it's a CAP/TASK category with
    # no canonical elements yet). Without a real place to put these, an
    # extraction model has no honest way to report "I found X but couldn't map
    # it" other than inventing a plausible-looking element_id -- which
    # prompts/P01_cv_extraction.txt explicitly forbids but has no field for.
    unmapped_terms: List[str] = Field(default_factory=list)
    unanswered_element_ids: List[str] = Field(default_factory=list)
    review_flags: List[str] = Field(default_factory=list)
