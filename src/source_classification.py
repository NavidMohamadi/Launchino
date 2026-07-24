from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import re


@dataclass(frozen=True)
class SourceClassification:
    classification: str
    source_id: str | None
    board_identifier: str | None
    company_domain: str | None
    recommended_action: str
    reason: str


def classify_vacancy_url(url: str) -> SourceClassification:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")

    if host.endswith("linkedin.com"):
        return SourceClassification(
            "blocked_direct_source", "linkedin_direct", None, None,
            "Do not fetch automatically; use an approved partner/API route or the employer's original career page.",
            "Direct LinkedIn automation is disabled by source policy.",
        )
    if host.endswith("indeed.com") or host.endswith("indeed.nl"):
        return SourceClassification(
            "blocked_direct_source", "indeed_direct", None, None,
            "Do not fetch automatically; locate the employer's original posting or use an approved Indeed partner route.",
            "Direct Indeed automation is disabled by source policy.",
        )
    greenhouse_match = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([^/]+)", url)
    if greenhouse_match:
        return SourceClassification(
            "approved_ats_api", "greenhouse_public_api", greenhouse_match.group(1), None,
            "Use the Greenhouse Job Board API.", "Recognised Greenhouse public board URL.",
        )
    if host == "jobs.lever.co" and path:
        return SourceClassification(
            "approved_ats_api", "lever_public_api", path.split("/")[0], None,
            "Use the Lever Postings API.", "Recognised Lever-hosted job URL.",
        )
    if host == "jobs.ashbyhq.com" and path:
        return SourceClassification(
            "approved_ats_api", "ashby_public_api", path.split("/")[0], None,
            "Use the Ashby public Job Postings API.", "Recognised Ashby-hosted job URL.",
        )
    if host:
        return SourceClassification(
            "needs_source_review", None, None, host,
            "Check whether this is the employer's official career page, review access conditions, and prefer JobPosting JSON-LD.",
            "The URL is not a recognised approved ATS route.",
        )
    return SourceClassification(
        "needs_source_review", None, None, None,
        "Request a valid URL or direct company submission.", "The URL could not be classified.",
    )
