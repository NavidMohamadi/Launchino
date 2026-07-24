import json
from pathlib import Path

from company_registry import CompanyRegistry
from job_sources.base import HttpResponse
from job_sources.greenhouse import GreenhouseAdapter
from source_policy import SourcePolicyRegistry
from vacancy_ingestion import VacancyIngestionService

ROOT = Path(__file__).resolve().parents[1]


class FixtureClient:
    def get(self, url, *, headers=None, timeout=20.0):
        payload = json.loads((ROOT / "data/fixtures/greenhouse_jobs.json").read_text())
        return HttpResponse(200, {"content-type": "application/json"}, json.dumps(payload), payload)


def test_ingestion_creates_then_deduplicates():
    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    companies = CompanyRegistry.from_json(ROOT / "data/company_registry_demo.json")
    service = VacancyIngestionService(policy_registry=policies, company_registry=companies)
    raw = GreenhouseAdapter().fetch("exampleanalytics", FixtureClient())[0]
    raw.company_name = "Example Analytics"
    raw.company_domain = "example-analytics.nl"
    first = service.ingest(raw)
    second = service.ingest(raw)
    assert first.created is True
    assert second.created is False
    assert second.duplicate_of == first.profile.vacancy_id
    assert len(service.repository.profiles) == 1


def test_ingestion_reopens_closed_vacancy_when_same_job_is_seen_again():
    from source_schemas import VacancyLifecycleStatus

    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    companies = CompanyRegistry.from_json(ROOT / "data/company_registry_demo.json")
    service = VacancyIngestionService(policy_registry=policies, company_registry=companies)
    raw = GreenhouseAdapter().fetch("exampleanalytics", FixtureClient())[0]
    raw.company_name = "Example Analytics"
    raw.company_domain = "example-analytics.nl"

    first = service.ingest(raw)
    closed = first.profile.model_copy(deep=True)
    closed.lifecycle_status = VacancyLifecycleStatus.CLOSED
    closed.closed_reason = "valid_through_expired"
    service.repository.save_profile(closed)

    observed = service.ingest(raw)
    assert observed.profile.lifecycle_status == VacancyLifecycleStatus.ACTIVE
    assert observed.profile.reopened_reason == "observed_again_after_closure"


def test_repository_uses_canonical_key_and_company_indexes_for_candidates():
    from canonical_vacancy import canonicalise_raw_vacancy
    from vacancy_ingestion import VacancyRepository

    repository = VacancyRepository()
    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    raw = GreenhouseAdapter().fetch("exampleanalytics", FixtureClient())[0]
    raw.company_name = "Example Analytics"
    raw.company_domain = "example-analytics.nl"
    target = canonicalise_raw_vacancy(raw, company_id="company-example")
    repository.save_profile(target)

    candidates = repository.duplicate_candidates(
        raw,
        resolved_company_id="company-example",
        resolved_company_domain="example-analytics.nl",
    )
    assert [p.vacancy_id for p in candidates] == [target.vacancy_id]
