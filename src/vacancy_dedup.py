from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Iterable

from source_schemas import CanonicalVacancyProfile, RawVacancyRecord, VacancyLifecycleStatus
from vacancy_utils import canonical_job_key, normalise_domain, normalise_text


class DuplicateOutcome(str, Enum):
    DUPLICATE = "duplicate"
    NOT_DUPLICATE = "not_duplicate"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class DuplicateDecision:
    outcome: DuplicateOutcome
    confidence: float
    reason: str
    matched_vacancy_id: str | None = None

    @property
    def duplicate(self) -> bool:
        return self.outcome == DuplicateOutcome.DUPLICATE

    @property
    def review_required(self) -> bool:
        return self.outcome == DuplicateOutcome.REVIEW_REQUIRED


def raw_canonical_key(
    raw: RawVacancyRecord,
    *,
    resolved_company_domain: str | None = None,
) -> str:
    return canonical_job_key(
        company_domain=resolved_company_domain or raw.company_domain,
        company_name=raw.company_name,
        title=raw.title,
        location=raw.location_text,
    )


def _company_identity_decision(
    raw: RawVacancyRecord,
    profile: CanonicalVacancyProfile,
    *,
    resolved_company_id: str | None,
    resolved_company_domain: str | None,
) -> tuple[str, float, str]:
    """Return (state, confidence, reason), where state is same/different/uncertain."""
    if resolved_company_id and profile.company_id:
        if resolved_company_id == profile.company_id:
            return "same", 1.0, "Same internal company ID"
        return "different", 1.0, "Internal company IDs differ"

    raw_domain = normalise_domain(resolved_company_domain or raw.company_domain)
    profile_domain = normalise_domain(profile.company_domain)
    if raw_domain and profile_domain:
        if raw_domain == profile_domain:
            return "same", 0.99, "Same normalised company domain"
        return "different", 1.0, "Company domains differ"

    raw_name = normalise_text(raw.company_name)
    profile_name = normalise_text(profile.company_name)
    if raw_name and profile_name and raw_name == profile_name:
        return "same", 0.96, "Exact normalised company name"

    name_similarity = SequenceMatcher(None, raw_name, profile_name).ratio() if raw_name and profile_name else 0.0
    if name_similarity >= 0.92:
        return "uncertain", round(name_similarity, 3), "Company names are highly similar but identity is unverified"
    return "different", round(name_similarity, 3), "Company identity does not match"


def compare_raw_to_profile(
    raw: RawVacancyRecord,
    profile: CanonicalVacancyProfile,
    *,
    resolved_company_id: str | None = None,
    resolved_company_domain: str | None = None,
) -> DuplicateDecision:
    # External IDs are the strongest source-specific identifier. An archived
    # record still requires review because the same ID can be reused for a repost.
    for source_id, external_id in profile.external_job_ids.items():
        if source_id == raw.source_id and raw.external_job_id and external_id == raw.external_job_id:
            if profile.lifecycle_status == VacancyLifecycleStatus.ARCHIVED:
                return DuplicateDecision(
                    DuplicateOutcome.REVIEW_REQUIRED,
                    1.0,
                    "Same source/external ID matches an archived vacancy; review as a possible repost",
                    profile.vacancy_id,
                )
            return DuplicateDecision(
                DuplicateOutcome.DUPLICATE,
                1.0,
                "Same source and external job ID",
                profile.vacancy_id,
            )

    identity_state, identity_confidence, identity_reason = _company_identity_decision(
        raw,
        profile,
        resolved_company_id=resolved_company_id,
        resolved_company_domain=resolved_company_domain,
    )
    if identity_state == "different":
        return DuplicateDecision(DuplicateOutcome.NOT_DUPLICATE, 0.0, identity_reason)
    if identity_state == "uncertain":
        return DuplicateDecision(
            DuplicateOutcome.REVIEW_REQUIRED,
            identity_confidence,
            identity_reason,
            profile.vacancy_id,
        )

    if profile.lifecycle_status == VacancyLifecycleStatus.ARCHIVED:
        return DuplicateDecision(
            DuplicateOutcome.REVIEW_REQUIRED,
            identity_confidence,
            "Possible match belongs to an archived vacancy; human review required",
            profile.vacancy_id,
        )

    incoming_key = raw_canonical_key(raw, resolved_company_domain=resolved_company_domain)
    if incoming_key == profile.canonical_key:
        return DuplicateDecision(
            DuplicateOutcome.DUPLICATE,
            max(identity_confidence, 0.98),
            f"Canonical key match after company identity check ({identity_reason})",
            profile.vacancy_id,
        )

    title_similarity = SequenceMatcher(None, normalise_text(raw.title), normalise_text(profile.title)).ratio()
    location_similarity = SequenceMatcher(
        None, normalise_text(raw.location_text), normalise_text(profile.location_text)
    ).ratio()
    combined = 0.85 * title_similarity + 0.15 * location_similarity
    if combined >= 0.92:
        return DuplicateDecision(
            DuplicateOutcome.DUPLICATE,
            round(combined, 3),
            f"High title/location similarity after company identity check ({identity_reason})",
            profile.vacancy_id,
        )
    if combined >= 0.82:
        return DuplicateDecision(
            DuplicateOutcome.REVIEW_REQUIRED,
            round(combined, 3),
            "Plausible same-company vacancy match but similarity is not decisive",
            profile.vacancy_id,
        )
    return DuplicateDecision(
        DuplicateOutcome.NOT_DUPLICATE,
        round(combined, 3),
        "Similarity below duplicate threshold",
    )


def find_duplicate(
    raw: RawVacancyRecord,
    profiles: Iterable[CanonicalVacancyProfile],
    *,
    resolved_company_id: str | None = None,
    resolved_company_domain: str | None = None,
) -> DuplicateDecision:
    best_duplicate: DuplicateDecision | None = None
    best_review: DuplicateDecision | None = None
    for profile in profiles:
        decision = compare_raw_to_profile(
            raw,
            profile,
            resolved_company_id=resolved_company_id,
            resolved_company_domain=resolved_company_domain,
        )
        if decision.duplicate and (best_duplicate is None or decision.confidence > best_duplicate.confidence):
            best_duplicate = decision
        elif decision.review_required and (best_review is None or decision.confidence > best_review.confidence):
            best_review = decision
    if best_duplicate:
        return best_duplicate
    if best_review:
        return best_review
    return DuplicateDecision(DuplicateOutcome.NOT_DUPLICATE, 0.0, "No existing vacancy matched")
