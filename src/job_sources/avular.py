from __future__ import annotations

import re

from bs4 import BeautifulSoup

from source_schemas import (
    AcquisitionMethod, RawVacancyRecord, SourceTrustLevel, VacancyIntakeSource,
)
from .base import HttpClient, JobSourceAdapter

DEFAULT_BASE_URL = "https://www.avular.com"

# Job listing links look like /careers/{slug} -- excludes the bare listing
# page itself and any query-string/fragment variant.
JOB_LINK_RE = re.compile(r"^/careers/[a-z0-9-]+$")

# The metadata line at the top of each job page reads (English):
#   "Location: X | Hours: Y | Employment type: Z"
# or (Dutch, seen live on at least one current posting):
#   "Locatie : X | Uren : Y | Dienstverband : Z"
# Both are genuinely part of Avular's current site, not a hypothetical future
# case, so both are handled explicitly -- anything else is treated as an
# unrecognised structure and raises rather than guessing.
_METADATA_PATTERNS = [
    re.compile(
        r"Location\s*:\s*(?P<location>[^|]+?)\s*\|\s*Hours\s*:\s*(?P<hours>[^|]+?)\s*\|\s*"
        r"Employment type\s*:\s*(?P<employment_type>.+)",
        re.I,
    ),
    re.compile(
        r"Locatie\s*:\s*(?P<location>[^|]+?)\s*\|\s*Uren\s*:\s*(?P<hours>[^|]+?)\s*\|\s*"
        r"Dienstverband\s*:\s*(?P<employment_type>.+)",
        re.I,
    ),
]


class AvularParseError(RuntimeError):
    """avular.com's careers pages no longer match the structure this narrow,
    single-site parser expects. Raised instead of returning wrong or
    garbled RawVacancyRecord data -- see AvularCareersAdapter's docstring."""


class AvularCareersAdapter(JobSourceAdapter):
    """Narrow, single-site parser for avular.com/careers.

    Not a general-purpose HTML scraper: every selector here is a specific
    structural assumption about Avular's current (Next.js) site, verified by
    hand against the live page before writing this. If Avular redesigns
    their careers page, the assumptions below will stop matching and this
    adapter is expected to raise AvularParseError rather than silently
    return incomplete or wrong records -- do not weaken these checks to
    "make it work" against a changed page; that defeats their purpose.

    source_id is registered in data/source_registry.json as needs_review,
    not approved -- src/source_policy.py's assert_allowed() will refuse to
    run this via the normal ingestion pipeline until a human flips that.
    """

    source_id = "avular_careers_html"

    def fetch(self, identifier: str, client: HttpClient) -> list[RawVacancyRecord]:
        base_url = (identifier or DEFAULT_BASE_URL).rstrip("/")
        slugs = self._list_job_slugs(base_url, client)

        records: list[RawVacancyRecord] = []
        for slug in slugs:
            url = f"{base_url}{slug}"
            response = client.get(url)
            if response.status_code != 200:
                raise AvularParseError(f"{url}: job page returned HTTP {response.status_code}")
            parsed = self._parse_job_page(response.text, url)
            records.append(RawVacancyRecord(
                source_id=self.source_id, source_record_id="avular-careers",
                intake_source=VacancyIntakeSource.PUBLIC_COMPANY_PAGE, acquisition_method=AcquisitionMethod.HTML,
                source_url=url, external_job_id=slug.rsplit("/", 1)[-1],
                company_name="Avular", company_domain="avular.com",
                title=parsed["title"], description_text=parsed["description_text"],
                location_text=parsed["location_text"],
                employment_types=[parsed["employment_type"]] if parsed["employment_type"] else [],
                apply_url=url, trust_level=SourceTrustLevel.OFFICIAL_COMPANY_PAGE,
            ))
        return records

    def _list_job_slugs(self, base_url: str, client: HttpClient) -> list[str]:
        listing_url = f"{base_url}/careers"
        response = client.get(listing_url)
        if response.status_code != 200:
            raise AvularParseError(f"{listing_url}: listing page returned HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        # Canary: confirms we're looking at the expected page section even
        # when there happen to be zero open roles, so "found the section but
        # no listings" (legitimately empty) is distinguishable from "this
        # isn't the page we think it is" (structure changed -- must raise).
        canary = soup.find(["h1", "h2"], string=lambda s: bool(s) and s.strip() == "Careers")
        if canary is None:
            raise AvularParseError(
                f"{listing_url}: expected 'Careers' section heading not found; "
                "page structure may have changed"
            )

        slugs: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if JOB_LINK_RE.match(href) and href not in seen:
                seen.add(href)
                slugs.append(href)
        return slugs

    def _parse_job_page(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        body_div = soup.find("div", class_=lambda c: c and "articleBody" in c)
        if body_div is None:
            raise AvularParseError(
                f"{url}: could not find the job description container (articleBody class); "
                "page structure may have changed"
            )

        title_el = next(iter(body_div.find_all_previous("h1")), None)
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            raise AvularParseError(f"{url}: could not find a non-empty job title heading")

        # Direct children only: <p>/<ul>/<ol> at the top level of the
        # description container, in document order. The first one is
        # always the Location/Hours/Employment type metadata line.
        blocks = [c for c in body_div.find_all(recursive=False) if getattr(c, "name", None) in ("p", "ul", "ol")]
        if not blocks:
            raise AvularParseError(f"{url}: job description container had no content blocks to parse")

        metadata_text = blocks[0].get_text(" ", strip=True)
        match = next((p.search(metadata_text) for p in _METADATA_PATTERNS if p.search(metadata_text)), None)
        if match is None:
            raise AvularParseError(
                f"{url}: could not parse the Location/Hours/Employment type line in either "
                f"the expected English or Dutch format; found: {metadata_text!r}"
            )

        description_text = "\n".join(
            text for b in blocks[1:] if (text := b.get_text(" ", strip=True))
        )
        if not description_text:
            raise AvularParseError(f"{url}: no description text found after the metadata line")

        return {
            "title": title,
            "location_text": match.group("location").strip(),
            "employment_type": match.group("employment_type").strip(),
            "description_text": description_text,
        }
