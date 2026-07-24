from canonical_vacancy import canonicalise_raw_vacancy
from source_schemas import RawVacancyRecord, SourceTrustLevel, VerificationStatus
from vacancy_dedup import compare_raw_to_profile
from vacancy_merge import merge_profile_fields


def raw(source_id="greenhouse_public_api", external_id="101", description="A"):
    return RawVacancyRecord(
        source_id=source_id, source_record_id="board", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com/jobs/101",
        external_job_id=external_id, company_name="Example B.V.", company_domain="example.com",
        title="Junior Supply Chain Analyst", description_text=description,
        location_text="Eindhoven", raw_payload={"id": external_id}, trust_level=4,
    )


def test_same_source_external_id_is_duplicate():
    profile = canonicalise_raw_vacancy(raw())
    decision = compare_raw_to_profile(raw(description="Changed"), profile)
    assert decision.duplicate is True
    assert decision.confidence == 1.0


def test_similar_cross_source_job_is_duplicate():
    profile = canonicalise_raw_vacancy(raw())
    incoming = raw(source_id="company_page_jsonld", external_id="other")
    incoming.acquisition_method = "json_ld"
    incoming.intake_source = "public_company_page"
    decision = compare_raw_to_profile(incoming, profile)
    assert decision.duplicate is True


def test_higher_trust_source_wins_conflict():
    profile = canonicalise_raw_vacancy(raw())
    merged = merge_profile_fields(
        profile,
        incoming_fields={"title": "Confirmed Supply Chain Analyst"},
        incoming_snapshot_id="company-confirmed",
        incoming_trust=SourceTrustLevel.COMPANY_CONFIRMED,
        incoming_verification=VerificationStatus.COMPANY_VALIDATED,
    )
    assert merged.title == "Confirmed Supply Chain Analyst"
    assert merged.source_conflicts[0].resolution_status == "resolved_by_source_precedence"


def test_generic_title_location_do_not_merge_different_companies_without_domains():
    from vacancy_dedup import DuplicateOutcome

    first = raw()
    first.company_name = "Alpha Software B.V."
    first.company_domain = None
    first.title = "Software Engineer"
    first.location_text = "Amsterdam"
    profile = canonicalise_raw_vacancy(first)

    incoming = raw(source_id="company_page_jsonld", external_id="202")
    incoming.company_name = "Beta Technology B.V."
    incoming.company_domain = None
    incoming.title = "Software Engineer"
    incoming.location_text = "Amsterdam"
    incoming.acquisition_method = "json_ld"
    incoming.intake_source = "public_company_page"

    decision = compare_raw_to_profile(incoming, profile)
    assert decision.outcome == DuplicateOutcome.NOT_DUPLICATE
    assert decision.duplicate is False


def test_highly_similar_unverified_company_names_require_review():
    from vacancy_dedup import DuplicateOutcome

    first = raw()
    first.company_name = "Example Technology Netherlands B.V."
    first.company_domain = None
    profile = canonicalise_raw_vacancy(first)

    incoming = raw(source_id="company_page_jsonld", external_id="202")
    incoming.company_name = "Example Technology Nederland B.V."
    incoming.company_domain = None
    incoming.acquisition_method = "json_ld"
    incoming.intake_source = "public_company_page"

    decision = compare_raw_to_profile(incoming, profile)
    assert decision.outcome == DuplicateOutcome.REVIEW_REQUIRED
    assert decision.review_required is True


def test_archived_possible_duplicate_requires_review_not_merge():
    from source_schemas import VacancyLifecycleStatus
    from vacancy_dedup import DuplicateOutcome

    profile = canonicalise_raw_vacancy(raw())
    profile.lifecycle_status = VacancyLifecycleStatus.ARCHIVED
    decision = compare_raw_to_profile(raw(), profile)
    assert decision.outcome == DuplicateOutcome.REVIEW_REQUIRED
