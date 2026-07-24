from __future__ import annotations

from typing import Dict

from canonical_vacancy import canonicalise_raw_vacancy
from company_registry import CompanyRegistry
from source_policy import SourcePolicyRegistry
from source_schemas import (
    CanonicalVacancyProfile,
    IngestionOutcome,
    RawVacancyRecord,
    SourceSnapshot,
    VerificationStatus,
)
from vacancy_dedup import find_duplicate, raw_canonical_key
from vacancy_lifecycle import mark_seen
from vacancy_merge import merge_profile_fields
from vacancy_utils import normalise_domain, normalise_text, stable_hash


class VacancyRepository:
    """In-memory reference repository with indexed duplicate candidate lookup.

    Replace with PostgreSQL lookups on source/external ID, canonical_key and
    company identity in production.
    """

    def __init__(self):
        self.profiles: Dict[str, CanonicalVacancyProfile] = {}
        self.snapshots: Dict[str, SourceSnapshot] = {}
        self._external_index: Dict[tuple[str, str], str] = {}
        self._canonical_index: Dict[str, set[str]] = {}
        self._company_id_index: Dict[str, set[str]] = {}
        self._company_domain_index: Dict[str, set[str]] = {}
        self._company_name_index: Dict[str, set[str]] = {}

    def list(self) -> list[CanonicalVacancyProfile]:
        return list(self.profiles.values())

    @staticmethod
    def _add(index: Dict[str, set[str]], key: str | None, vacancy_id: str) -> None:
        if key:
            index.setdefault(key, set()).add(vacancy_id)

    @staticmethod
    def _remove(index: Dict[str, set[str]], key: str | None, vacancy_id: str) -> None:
        if key and key in index:
            index[key].discard(vacancy_id)
            if not index[key]:
                del index[key]

    def _deindex(self, profile: CanonicalVacancyProfile) -> None:
        for source_id, external_id in profile.external_job_ids.items():
            self._external_index.pop((source_id, external_id), None)
        self._remove(self._canonical_index, profile.canonical_key, profile.vacancy_id)
        self._remove(self._company_id_index, profile.company_id, profile.vacancy_id)
        self._remove(self._company_domain_index, normalise_domain(profile.company_domain), profile.vacancy_id)
        self._remove(self._company_name_index, normalise_text(profile.company_name), profile.vacancy_id)

    def save_profile(self, profile: CanonicalVacancyProfile) -> None:
        previous = self.profiles.get(profile.vacancy_id)
        if previous:
            self._deindex(previous)
        self.profiles[profile.vacancy_id] = profile
        for source_id, external_id in profile.external_job_ids.items():
            self._external_index[(source_id, external_id)] = profile.vacancy_id
        self._add(self._canonical_index, profile.canonical_key, profile.vacancy_id)
        self._add(self._company_id_index, profile.company_id, profile.vacancy_id)
        self._add(self._company_domain_index, normalise_domain(profile.company_domain), profile.vacancy_id)
        self._add(self._company_name_index, normalise_text(profile.company_name), profile.vacancy_id)

    def save_snapshot(self, snapshot: SourceSnapshot) -> None:
        self.snapshots[snapshot.snapshot_id] = snapshot

    def duplicate_candidates(
        self,
        raw: RawVacancyRecord,
        *,
        resolved_company_id: str | None,
        resolved_company_domain: str | None,
    ) -> list[CanonicalVacancyProfile]:
        """Generate a small candidate set before fuzzy comparison."""
        ids: set[str] = set()
        if raw.external_job_id:
            vacancy_id = self._external_index.get((raw.source_id, raw.external_job_id))
            if vacancy_id:
                ids.add(vacancy_id)

        key = raw_canonical_key(raw, resolved_company_domain=resolved_company_domain)
        ids.update(self._canonical_index.get(key, set()))

        if resolved_company_id:
            ids.update(self._company_id_index.get(resolved_company_id, set()))
        domain = normalise_domain(resolved_company_domain or raw.company_domain)
        if domain:
            ids.update(self._company_domain_index.get(domain, set()))
        ids.update(self._company_name_index.get(normalise_text(raw.company_name), set()))

        return [self.profiles[vacancy_id] for vacancy_id in sorted(ids)]


class VacancyIngestionService:
    def __init__(
        self,
        *,
        policy_registry: SourcePolicyRegistry,
        company_registry: CompanyRegistry | None = None,
        repository: VacancyRepository | None = None,
    ):
        self.policy_registry = policy_registry
        self.company_registry = company_registry
        self.repository = repository or VacancyRepository()

    def _snapshot(self, raw: RawVacancyRecord) -> SourceSnapshot:
        payload = raw.raw_payload or raw.model_dump(mode="json")
        content_hash = stable_hash(payload)
        snapshot_id = f"snap-{raw.source_id}-{content_hash[:16]}"
        return SourceSnapshot(
            snapshot_id=snapshot_id,
            source_record_id=raw.source_record_id,
            source_id=raw.source_id,
            source_url=raw.source_url,
            external_job_id=raw.external_job_id,
            retrieved_at=raw.retrieved_at,
            content_hash=content_hash,
            raw_payload=payload,
            trust_level=raw.trust_level,
        )

    def ingest(self, raw: RawVacancyRecord) -> IngestionOutcome:
        self.policy_registry.assert_allowed(raw.source_id, raw.acquisition_method)
        snapshot = self._snapshot(raw)
        self.repository.save_snapshot(snapshot)

        company = None
        if self.company_registry:
            company = self.company_registry.find_company(name=raw.company_name, domain=raw.company_domain)
        resolved_company_id = company.company_id if company else None
        resolved_company_domain = company.website_domain if company else raw.company_domain

        candidates = self.repository.duplicate_candidates(
            raw,
            resolved_company_id=resolved_company_id,
            resolved_company_domain=resolved_company_domain,
        )
        duplicate = find_duplicate(
            raw,
            candidates,
            resolved_company_id=resolved_company_id,
            resolved_company_domain=resolved_company_domain,
        )

        if duplicate.review_required:
            existing = self.repository.profiles[duplicate.matched_vacancy_id]
            return IngestionOutcome(
                profile=existing,
                created=False,
                updated=False,
                duplicate_of=existing.vacancy_id,
                review_flags=["possible_duplicate_needs_review", duplicate.reason],
                confidence=duplicate.confidence,
                snapshot_id=snapshot.snapshot_id,
            )

        if not duplicate.duplicate:
            profile = canonicalise_raw_vacancy(
                raw,
                company_id=resolved_company_id,
                company_domain=resolved_company_domain,
                snapshot_id=snapshot.snapshot_id,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            )
            self.repository.save_profile(profile)
            review_flags = []
            if not company:
                review_flags.append("company_identity_needs_review")
            if not raw.external_job_id:
                review_flags.append("external_job_id_missing")
            return IngestionOutcome(
                profile=profile, created=True, updated=False, review_flags=review_flags,
                confidence=duplicate.confidence, snapshot_id=snapshot.snapshot_id,
            )

        existing = self.repository.profiles[duplicate.matched_vacancy_id]
        incoming_fields = {
            "title": raw.title,
            "description_text": raw.description_text,
            "location_text": raw.location_text,
            "department": raw.department,
            "employment_types": raw.employment_types,
            "work_mode": raw.work_mode,
            "apply_url": raw.apply_url,
            "date_posted": raw.date_posted,
            "valid_through": raw.valid_through,
            "salary": raw.salary,
            "company_domain": resolved_company_domain,
        }
        merged = merge_profile_fields(
            existing,
            incoming_fields=incoming_fields,
            incoming_snapshot_id=snapshot.snapshot_id,
            incoming_trust=raw.trust_level,
            incoming_verification=VerificationStatus.SOURCE_VERIFIED,
        )
        if raw.external_job_id:
            merged.external_job_ids[raw.source_id] = raw.external_job_id
        if raw.intake_source not in merged.intake_sources:
            merged.intake_sources.append(raw.intake_source)
        if raw.acquisition_method not in merged.acquisition_methods:
            merged.acquisition_methods.append(raw.acquisition_method)
        if snapshot.snapshot_id not in merged.source_snapshot_ids:
            merged.source_snapshot_ids.append(snapshot.snapshot_id)

        # Recompute the canonical content fingerprint after precedence-based merge.
        # mark_seen is called after merge so a directly observed CLOSED vacancy is
        # reactivated even when its canonical content is unchanged.
        canonical_content_hash = stable_hash({
            "title": merged.title,
            "description": merged.description_text,
            "location": merged.location_text,
        })
        merge_incremented_version = merged.version > existing.version
        merged = mark_seen(
            merged,
            content_hash=canonical_content_hash,
            seen_at=raw.retrieved_at,
            increment_version=not merge_incremented_version,
        )
        self.repository.save_profile(merged)
        return IngestionOutcome(
            profile=merged,
            created=False,
            updated=merged.version > existing.version,
            duplicate_of=existing.vacancy_id,
            review_flags=["source_conflict_review"] if merged.source_conflicts else [],
            confidence=duplicate.confidence,
            snapshot_id=snapshot.snapshot_id,
        )
