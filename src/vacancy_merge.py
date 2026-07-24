from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable

from source_schemas import (
    CanonicalVacancyProfile, SourceConflict, SourceTrustLevel, VerificationStatus,
)


VERIFICATION_RANK = {
    VerificationStatus.AUTO_EXTRACTED: 1,
    VerificationStatus.SOURCE_VERIFIED: 2,
    VerificationStatus.HUMAN_REVIEWED: 3,
    VerificationStatus.COMPANY_VALIDATED: 4,
}


def _source_rank(trust: SourceTrustLevel, verification: VerificationStatus) -> int:
    return int(trust) * 10 + VERIFICATION_RANK[verification]


def choose_field_value(
    *, field_path: str, current_value: Any, incoming_value: Any,
    current_rank: int, incoming_rank: int, current_snapshot_id: str,
    incoming_snapshot_id: str,
) -> tuple[Any, SourceConflict | None, bool]:
    if incoming_value in (None, "", [], {}):
        return current_value, None, False
    if current_value in (None, "", [], {}):
        return incoming_value, None, True
    if current_value == incoming_value:
        return current_value, None, False
    conflict = SourceConflict(
        field_path=field_path,
        values_by_snapshot={current_snapshot_id: current_value, incoming_snapshot_id: incoming_value},
    )
    if incoming_rank > current_rank:
        conflict.resolution_status = "resolved_by_source_precedence"
        conflict.resolved_value = incoming_value
        conflict.resolution_note = "Higher-trust or more-verified source selected automatically."
        return incoming_value, conflict, True
    conflict.resolution_status = "resolved_by_source_precedence"
    conflict.resolved_value = current_value
    conflict.resolution_note = "Existing higher-trust or more-verified source retained."
    return current_value, conflict, False


def merge_profile_fields(
    profile: CanonicalVacancyProfile,
    *, incoming_fields: Dict[str, Any], incoming_snapshot_id: str,
    incoming_trust: SourceTrustLevel,
    incoming_verification: VerificationStatus,
) -> CanonicalVacancyProfile:
    updated = profile.model_copy(deep=True)
    current_snapshot_id = profile.source_snapshot_ids[-1] if profile.source_snapshot_ids else "existing"
    current_trust = max((p.source_trust_level for p in profile.provenance), default=SourceTrustLevel.UNVERIFIED)
    current_verification = profile.verification_status
    current_rank = _source_rank(current_trust, current_verification)
    incoming_rank = _source_rank(incoming_trust, incoming_verification)
    changed = False
    supported_fields = {
        "title", "description_text", "location_text", "department", "employment_types",
        "work_mode", "apply_url", "date_posted", "valid_through", "salary", "company_domain",
    }
    for field_path, incoming_value in incoming_fields.items():
        if field_path not in supported_fields:
            continue
        current_value = getattr(updated, field_path)
        selected, conflict, field_changed = choose_field_value(
            field_path=field_path,
            current_value=current_value,
            incoming_value=incoming_value,
            current_rank=current_rank,
            incoming_rank=incoming_rank,
            current_snapshot_id=current_snapshot_id,
            incoming_snapshot_id=incoming_snapshot_id,
        )
        setattr(updated, field_path, selected)
        if conflict:
            updated.source_conflicts.append(conflict)
        changed = changed or field_changed
    if incoming_snapshot_id not in updated.source_snapshot_ids:
        updated.source_snapshot_ids.append(incoming_snapshot_id)
    if changed:
        updated.version += 1
    if VERIFICATION_RANK[incoming_verification] > VERIFICATION_RANK[updated.verification_status]:
        updated.verification_status = incoming_verification
    return updated
