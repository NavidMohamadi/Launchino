"""End-to-end scenario: a company submits a vacancy directly through the
form (source_id=company_direct_form), and the same job is later discovered
by the ingestion pipeline via an approved scraped source (here, the
employer's own career page JSON-LD; company_page_jsonld). Confirms that
vacancy_dedup recognises the scrape as the same vacancy rather than
creating a duplicate, and that vacancy_merge keeps every company-answered
field even when the scrape disagrees, filling in only what the company
left blank.
"""

from pathlib import Path

from canonical_vacancy import DEFAULT_PUBLIC_WEIGHTS
from company_intake import canonicalise_company_submission
from job_sources.jsonld import JsonLdJobPostingAdapter
from source_policy import SourcePolicyRegistry
from source_schemas import RawVacancyRecord, VerificationStatus
from vacancy_ingestion import VacancyIngestionService

ROOT = Path(__file__).resolve().parents[1]

COMPANY_DESCRIPTION = (
    "Support our supply chain team with inventory analysis and supplier "
    "coordination across three regional warehouses."
)

# Same title/location/domain as the company submission below (same real job),
# but a different description, plus salary/work-mode/employment-type/apply-url/
# valid-through details the company submission never provided.
SCRAPED_JOBPOSTING_HTML = """
<!doctype html>
<html><head><title>Supply Chain Intern</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "identifier": {"@type": "PropertyValue", "name": "Example Foods", "value": "SC-999"},
  "title": "Supply Chain Intern",
  "description": "<p>Help the supply chain team keep inventory accurate and coordinate with suppliers.</p>",
  "datePosted": "2026-07-20",
  "validThrough": "2026-09-30",
  "employmentType": "INTERN",
  "jobLocationType": "TELECOMMUTE",
  "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR", "value": {"@type": "QuantitativeValue", "value": 1200, "unitText": "MONTH"}},
  "hiringOrganization": {"@type": "Organization", "name": "Example Foods B.V.", "sameAs": "https://example-foods.nl"},
  "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Tilburg", "addressCountry": "NL"}},
  "url": "https://example-foods.nl/careers/sc-999"
}
</script></head><body><h1>Supply Chain Intern</h1></body></html>
"""


def _company_submission_profile():
    submission = {
        "company_name": "Example Foods B.V.",
        "company_domain": "example-foods.nl",
        "title": "Supply Chain Intern",
        "description_text": COMPANY_DESCRIPTION,
        "location_text": "Tilburg, NL",
        # department, employment_types, work_mode, apply_url, date_posted,
        # valid_through and salary are deliberately left unanswered.
    }
    return canonicalise_company_submission(
        submission, company_id="company-example-foods", category_weights=DEFAULT_PUBLIC_WEIGHTS,
    )


def test_company_direct_vacancy_deduplicates_against_scraped_jsonld_and_keeps_company_fields():
    company_profile = _company_submission_profile()
    assert company_profile.intake_sources == ["company_direct"]
    assert company_profile.external_job_ids == {}
    assert company_profile.verification_status == VerificationStatus.COMPANY_VALIDATED

    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    service = VacancyIngestionService(policy_registry=policies)
    # The company profile did not arrive through ingest(); seed the
    # repository the way persisting a company-direct submission would.
    service.repository.save_profile(company_profile)

    scraped_raw = JsonLdJobPostingAdapter().parse(
        html=SCRAPED_JOBPOSTING_HTML, page_url="https://example-foods.nl/careers/sc-999",
    )[0]

    outcome = service.ingest(scraped_raw)

    # 1. Dedup: the scrape is recognised as the same vacancy, not a new one.
    assert outcome.created is False
    assert outcome.duplicate_of == company_profile.vacancy_id
    assert len(service.repository.profiles) == 1

    merged = outcome.profile

    # 2. Merge: fields the company answered survive even though the scrape
    #    disagrees (description_text) or agrees (title/location_text).
    assert merged.title == "Supply Chain Intern"
    assert merged.location_text == "Tilburg, NL"
    assert merged.description_text == COMPANY_DESCRIPTION
    assert merged.verification_status == VerificationStatus.COMPANY_VALIDATED

    conflicts_by_field = {c.field_path: c for c in merged.source_conflicts}
    assert "description_text" in conflicts_by_field
    assert conflicts_by_field["description_text"].resolution_status == "resolved_by_source_precedence"
    assert conflicts_by_field["description_text"].resolved_value == COMPANY_DESCRIPTION
    assert "title" not in conflicts_by_field  # identical on both sides, never a conflict
    assert "location_text" not in conflicts_by_field

    # 3. Merge: fields the company left blank are filled in from the scrape.
    assert merged.work_mode == "telecommute"
    assert merged.apply_url == "https://example-foods.nl/careers/sc-999"
    assert merged.employment_types == ["INTERN"]
    assert merged.valid_through.isoformat() == "2026-09-30"
    assert merged.salary["value"]["value"] == 1200

    # Fields blank on both sides simply stay blank.
    assert merged.department is None

    # Provenance from both sources is retained.
    assert merged.external_job_ids.get("company_page_jsonld") == "SC-999"
    assert set(merged.intake_sources) == {"company_direct", "public_company_page"}


def test_review_required_outcome_exposes_confidence_and_snapshot_id():
    """Same shape as the real ambiguous cases found on live Greenhouse data
    (see PROJECT_NOTES.md): identical title, different real-world location.
    vacancy_dedup correctly can't decide "same role, separate posting" vs
    "accidental duplicate" from text alone, so it's review_required -- and
    IngestionOutcome must expose the confidence/snapshot_id behind that
    decision so a caller (api/ingestion_store.insert_vacancy_dedup_review)
    can persist it without re-deriving either value itself."""
    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    service = VacancyIngestionService(policy_registry=policies)

    first = RawVacancyRecord(
        source_id="greenhouse_public_api", source_record_id="acme", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com/jobs/1", external_job_id="1",
        company_name="Acme Corp", company_domain="acme.example",
        title="Engineering Manager, Cloud Platform", description_text="Lead the cloud platform team.",
        location_text="British Columbia", trust_level=4,
    )
    first_outcome = service.ingest(first)
    assert first_outcome.created is True
    assert first_outcome.confidence is not None
    assert first_outcome.snapshot_id in service.repository.snapshots

    second = RawVacancyRecord(
        source_id="greenhouse_public_api", source_record_id="acme", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com/jobs/2", external_job_id="2",
        company_name="Acme Corp", company_domain="acme.example",
        title="Engineering Manager, Cloud Platform", description_text="Lead the cloud platform team.",
        location_text="Ontario", trust_level=4,
    )
    outcome = service.ingest(second)

    assert outcome.created is False
    assert outcome.duplicate_of == first_outcome.profile.vacancy_id
    assert "possible_duplicate_needs_review" in outcome.review_flags

    assert outcome.confidence is not None
    assert 0.0 <= outcome.confidence <= 1.0
    assert outcome.snapshot_id is not None
    assert outcome.snapshot_id in service.repository.snapshots
    assert outcome.snapshot_id != first_outcome.snapshot_id
