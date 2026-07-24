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


class GreenhouseAdapter(JobSourceAdapter):
    source_id = "greenhouse_public_api"

    def fetch(self, identifier: str, client: HttpClient) -> list[RawVacancyRecord]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{identifier}/jobs?content=true"
        response = client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Greenhouse returned HTTP {response.status_code}")
        payload = response.json()
        rows = payload.get("jobs", [])
        output: list[RawVacancyRecord] = []
        for row in rows:
            location = (row.get("location") or {}).get("name")
            departments = [x.get("name") for x in row.get("departments", []) if x.get("name")]
            date_posted = None
            for key in ("updated_at", "created_at"):
                raw_date = row.get(key)
                if raw_date:
                    try:
                        date_posted = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
                        break
                    except ValueError:
                        pass
            output.append(RawVacancyRecord(
                source_id=self.source_id,
                source_record_id=identifier,
                intake_source=VacancyIntakeSource.PUBLIC_ATS_API,
                acquisition_method=AcquisitionMethod.API,
                source_url=row.get("absolute_url") or url,
                external_job_id=str(row.get("id")),
                company_name=identifier,
                title=row.get("title", "Untitled vacancy"),
                description_html=row.get("content") or "",
                description_text=_strip_html(row.get("content")),
                location_text=location,
                department=", ".join(departments) or None,
                apply_url=row.get("absolute_url"),
                date_posted=date_posted,
                raw_payload=row,
                trust_level=SourceTrustLevel.OFFICIAL_ATS,
            ))
        return output
