from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Iterable

from bs4 import BeautifulSoup

from source_schemas import (
    AcquisitionMethod, RawVacancyRecord, SourceTrustLevel, VacancyIntakeSource,
)


def _walk_json(value: Any) -> Iterable[dict]:
    if isinstance(value, dict):
        if value.get("@type") == "JobPosting" or "JobPosting" in (value.get("@type") or []):
            yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _location_text(value: Any) -> str | None:
    if not value:
        return None
    values = value if isinstance(value, list) else [value]
    out = []
    for row in values:
        if isinstance(row, str):
            out.append(row)
            continue
        address = (row or {}).get("address") if isinstance(row, dict) else None
        if isinstance(address, str):
            out.append(address)
        elif isinstance(address, dict):
            bits = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            out.append(", ".join(str(x) for x in bits if x))
    return "; ".join(x for x in out if x) or None


class JsonLdJobPostingAdapter:
    source_id = "company_page_jsonld"

    def parse(self, *, html: str, page_url: str, source_record_id: str = "manual") -> list[RawVacancyRecord]:
        soup = BeautifulSoup(html, "html.parser")
        output: list[RawVacancyRecord] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            for row in _walk_json(payload):
                org = row.get("hiringOrganization") or {}
                identifier = row.get("identifier") or {}
                external_id = identifier.get("value") if isinstance(identifier, dict) else identifier
                employment = row.get("employmentType")
                employment_types = employment if isinstance(employment, list) else ([employment] if employment else [])
                description_html = str(row.get("description") or "")
                description_text = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
                output.append(RawVacancyRecord(
                    source_id=self.source_id,
                    source_record_id=source_record_id,
                    intake_source=VacancyIntakeSource.PUBLIC_COMPANY_PAGE,
                    acquisition_method=AcquisitionMethod.JSON_LD,
                    source_url=page_url,
                    external_job_id=str(external_id) if external_id else None,
                    company_name=org.get("name") or "Unknown company",
                    company_domain=org.get("sameAs"),
                    title=row.get("title") or row.get("name") or "Untitled vacancy",
                    description_html=description_html,
                    description_text=description_text,
                    location_text=_location_text(row.get("jobLocation")),
                    employment_types=[str(x) for x in employment_types],
                    work_mode=str(row.get("jobLocationType") or "").lower() or None,
                    apply_url=row.get("url") or page_url,
                    date_posted=_parse_date(row.get("datePosted")),
                    valid_through=_parse_date(row.get("validThrough")),
                    salary=row.get("baseSalary") if isinstance(row.get("baseSalary"), dict) else None,
                    raw_payload=row,
                    trust_level=SourceTrustLevel.OFFICIAL_COMPANY_PAGE,
                ))
        return output
