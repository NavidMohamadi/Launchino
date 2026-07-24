from __future__ import annotations

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


def main():
    policies = SourcePolicyRegistry.from_json(ROOT / "data/source_registry.json")
    companies = CompanyRegistry.from_json(ROOT / "data/company_registry_demo.json")
    service = VacancyIngestionService(policy_registry=policies, company_registry=companies)

    raw = GreenhouseAdapter().fetch("exampleanalytics", FixtureClient())[0]
    raw.company_name = "Example Analytics"
    raw.company_domain = "example-analytics.nl"
    outcome = service.ingest(raw)
    print(json.dumps(outcome.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
