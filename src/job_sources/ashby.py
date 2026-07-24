from __future__ import annotations

from datetime import datetime
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


class AshbyAdapter(JobSourceAdapter):
    source_id = "ashby_public_api"

    def fetch(self, identifier: str, client: HttpClient) -> list[RawVacancyRecord]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{identifier}"
        response = client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Ashby returned HTTP {response.status_code}")
        payload = response.json()
        output: list[RawVacancyRecord] = []
        for row in payload.get("jobs", []):
            published = row.get("publishedAt")
            date_posted = None
            if published:
                try:
                    date_posted = datetime.fromisoformat(published.replace("Z", "+00:00")).date()
                except ValueError:
                    pass
            output.append(RawVacancyRecord(
                source_id=self.source_id,
                source_record_id=identifier,
                intake_source=VacancyIntakeSource.PUBLIC_ATS_API,
                acquisition_method=AcquisitionMethod.API,
                source_url=row.get("jobUrl") or url,
                external_job_id=str(row.get("id") or row.get("jobPostingId") or row.get("title")),
                company_name=identifier,
                title=row.get("title", "Untitled vacancy"),
                description_html=row.get("descriptionHtml") or row.get("description") or "",
                description_text=_strip_html(row.get("descriptionHtml") or row.get("description")),
                location_text=row.get("location"),
                department=row.get("department"),
                employment_types=[row.get("employmentType")] if row.get("employmentType") else [],
                work_mode="remote" if row.get("isRemote") else None,
                apply_url=row.get("applyUrl") or row.get("jobUrl"),
                date_posted=date_posted,
                raw_payload=row,
                trust_level=SourceTrustLevel.OFFICIAL_ATS,
            ))
        return output
