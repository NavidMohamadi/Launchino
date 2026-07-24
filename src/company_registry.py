from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable

from source_schemas import CompanyJobSource, CompanyRecord
from vacancy_utils import normalise_domain, normalise_text


class CompanyRegistry:
    def __init__(self, companies: Dict[str, CompanyRecord], sources: list[CompanyJobSource]):
        self.companies = companies
        self.sources = sources

    @classmethod
    def from_json(cls, path: str | Path) -> "CompanyRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        companies = {
            row["company_id"]: CompanyRecord.model_validate(row)
            for row in payload.get("companies", [])
        }
        sources = [CompanyJobSource.model_validate(row) for row in payload.get("sources", [])]
        return cls(companies, sources)

    def find_company(self, *, name: str | None = None, domain: str | None = None) -> CompanyRecord | None:
        target_domain = normalise_domain(domain)
        if target_domain:
            for company in self.companies.values():
                if normalise_domain(company.website_domain) == target_domain:
                    return company
        target_name = normalise_text(name)
        if target_name:
            for company in self.companies.values():
                if normalise_text(company.legal_name) == target_name or normalise_text(company.display_name) == target_name:
                    return company
        return None

    def active_sources(self) -> list[CompanyJobSource]:
        return [row for row in self.sources if row.enabled and self.companies.get(row.company_id, None) and self.companies[row.company_id].active]
