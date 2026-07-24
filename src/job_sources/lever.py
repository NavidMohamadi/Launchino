from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re

from source_schemas import (
    AcquisitionMethod, RawVacancyRecord, SourceTrustLevel, VacancyIntakeSource,
)
from .base import HttpClient, JobSourceAdapter


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value))).strip()


class LeverAdapter(JobSourceAdapter):
    source_id = "lever_public_api"

    def fetch(self, identifier: str, client: HttpClient) -> list[RawVacancyRecord]:
        url = f"https://api.lever.co/v0/postings/{identifier}?mode=json"
        response = client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Lever returned HTTP {response.status_code}")
        output: list[RawVacancyRecord] = []
        for row in response.json():
            categories = row.get("categories") or {}
            created = row.get("createdAt")
            date_posted = None
            if isinstance(created, (int, float)):
                date_posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date()
            html = row.get("descriptionPlain") or row.get("description") or ""
            output.append(RawVacancyRecord(
                source_id=self.source_id,
                source_record_id=identifier,
                intake_source=VacancyIntakeSource.PUBLIC_ATS_API,
                acquisition_method=AcquisitionMethod.API,
                source_url=row.get("hostedUrl") or url,
                external_job_id=str(row.get("id")),
                company_name=identifier,
                title=row.get("text", "Untitled vacancy"),
                description_html=row.get("description") or None,
                description_text=_strip_html(html),
                location_text=categories.get("location"),
                department=categories.get("department") or categories.get("team"),
                employment_types=[categories.get("commitment")] if categories.get("commitment") else [],
                apply_url=row.get("applyUrl") or row.get("hostedUrl"),
                date_posted=date_posted,
                raw_payload=row,
                trust_level=SourceTrustLevel.OFFICIAL_ATS,
            ))
        return output
