from pathlib import Path
import pytest

from source_policy import SourcePolicyError, SourcePolicyRegistry
from source_schemas import AcquisitionMethod


ROOT = Path(__file__).resolve().parents[1]


def test_official_ats_api_is_allowed():
    registry = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    policy = registry.assert_allowed("greenhouse_public_api", AcquisitionMethod.API)
    assert policy.enabled is True


def test_linkedin_direct_is_blocked():
    registry = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    with pytest.raises(SourcePolicyError):
        registry.assert_allowed("linkedin_direct", AcquisitionMethod.HTML)


def test_indeed_partner_requires_approval():
    registry = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    with pytest.raises(SourcePolicyError):
        registry.assert_allowed("indeed_partner", AcquisitionMethod.API)


def test_needs_review_is_blocked_even_if_enabled():
    from source_schemas import SourcePolicy, TermsReviewStatus, RobotsPolicy

    policy = SourcePolicy(
        source_id="experimental_html",
        display_name="Experimental HTML source",
        enabled=True,
        terms_review_status=TermsReviewStatus.NEEDS_REVIEW,
        allowed_methods=[AcquisitionMethod.HTML],
        robots_policy=RobotsPolicy.RESPECT,
    )
    registry = SourcePolicyRegistry({policy.source_id: policy})
    with pytest.raises(SourcePolicyError, match="not approved"):
        registry.assert_allowed(policy.source_id, AcquisitionMethod.HTML)
