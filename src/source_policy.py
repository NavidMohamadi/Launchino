from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from source_schemas import AcquisitionMethod, SourcePolicy, TermsReviewStatus


class SourcePolicyError(RuntimeError):
    pass


class SourcePolicyRegistry:
    def __init__(self, policies: Dict[str, SourcePolicy]):
        self.policies = policies

    @classmethod
    def from_json(cls, path: str | Path) -> "SourcePolicyRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({row["source_id"]: SourcePolicy.model_validate(row) for row in data})

    def get(self, source_id: str) -> SourcePolicy:
        try:
            return self.policies[source_id]
        except KeyError as exc:
            raise SourcePolicyError(f"Unknown source_id: {source_id}") from exc

    def assert_allowed(self, source_id: str, method: AcquisitionMethod) -> SourcePolicy:
        """Fail closed unless the exact route is enabled and explicitly approved."""
        policy = self.get(source_id)

        if policy.terms_review_status != TermsReviewStatus.APPROVED:
            raise SourcePolicyError(
                f"{policy.display_name} is not approved for automated acquisition "
                f"(status={policy.terms_review_status.value})"
            )
        if not policy.enabled:
            raise SourcePolicyError(f"{policy.display_name} is disabled")
        if method not in policy.allowed_methods:
            raise SourcePolicyError(f"Method {method.value} is not approved for {policy.display_name}")
        if policy.partner_approval_required:
            raise SourcePolicyError(f"Partner approval is required for {policy.display_name}")

        # Defence in depth: keep the model's single permits() rule aligned with
        # this guard and fail if future changes create a discrepancy.
        if not policy.permits(method):
            raise SourcePolicyError(f"{policy.display_name} does not permit method {method.value}")
        return policy
