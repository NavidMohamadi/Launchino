"""AvularCareersAdapter is a narrow, single-site parser (src/job_sources/avular.py),
not a general HTML scraper -- these tests confirm it extracts real-shaped
content correctly and, just as importantly, that it fails loudly rather than
silently returning wrong/garbled data when the expected structure isn't there.
Fixture HTML mirrors the real page structure verified by hand against the
live site (see PROJECT_NOTES.md / the source_registry.json entry's notes).
"""

import pytest

from job_sources.avular import AvularCareersAdapter, AvularParseError
from job_sources.base import HttpResponse

LISTING_HTML = """
<html><body>
<h2>Careers</h2>
<a href="/careers/test-engineer">Read more</a>
<a href="/careers/office-manager">Read more</a>
<a href="/some-other-link">Not a job</a>
</body></html>
"""

EMPTY_LISTING_HTML = """
<html><body>
<h2>Careers</h2>
<p>No open positions right now.</p>
</body></html>
"""

BROKEN_LISTING_HTML = "<html><body><h1>Avular</h1><p>Redesigned site.</p></body></html>"

JOB_HTML_EN = """
<html><body>
<h1>Some decorative hero title</h1>
<h1>Test Engineer</h1>
<hr/>
<div class="articlePage-module-scss-module__xyz__articleBody">
<p><strong>Location: </strong>Eindhoven (Strijp-T) | <strong>Hours: </strong>40 hours per week | <strong>Employment type: </strong>Direct employment</p>
<p>We are looking for a Test Engineer to join the team.</p>
<ul><li>Define test strategy</li><li>Own integration testing</li></ul>
</div>
</body></html>
"""

JOB_HTML_NL = """
<html><body>
<h1>Office Manager</h1>
<hr/>
<div class="articlePage-module-scss-module__abc__articleBody">
<p><strong>Locatie : </strong>Eindhoven (Strijp-T) | <strong>Uren : </strong>32 uur per week | <strong>Dienstverband : </strong>Vast dienstverband</p>
<p>Wij zoeken een Office Manager.</p>
</div>
</body></html>
"""

JOB_HTML_NO_ARTICLE_BODY = "<html><body><h1>Test Engineer</h1><p>Some unrelated content.</p></body></html>"

JOB_HTML_UNPARSEABLE_METADATA = """
<html><body>
<h1>Test Engineer</h1>
<div class="articlePage-module-scss-module__xyz__articleBody">
<p>Somewhere, sometime, some hours.</p>
<p>Description text.</p>
</div>
</body></html>
"""


class FixtureClient:
    def __init__(self, pages: dict):
        self.pages = pages

    def get(self, url, *, headers=None, timeout=20.0):
        for suffix, html in self.pages.items():
            if url.endswith(suffix):
                return HttpResponse(200, {"content-type": "text/html"}, html)
        return HttpResponse(404, {}, "not found")


def test_fetch_extracts_english_and_dutch_postings():
    client = FixtureClient({
        "/careers": LISTING_HTML,
        "/careers/test-engineer": JOB_HTML_EN,
        "/careers/office-manager": JOB_HTML_NL,
    })
    records = AvularCareersAdapter().fetch("https://www.avular.com", client)

    assert len(records) == 2
    by_id = {r.external_job_id: r for r in records}

    en = by_id["test-engineer"]
    assert en.title == "Test Engineer"
    assert en.location_text == "Eindhoven (Strijp-T)"
    assert en.employment_types == ["Direct employment"]
    assert "test strategy" in en.description_text
    assert en.company_name == "Avular"
    assert en.source_url == "https://www.avular.com/careers/test-engineer"

    nl = by_id["office-manager"]
    assert nl.title == "Office Manager"
    assert nl.location_text == "Eindhoven (Strijp-T)"
    assert nl.employment_types == ["Vast dienstverband"]


def test_fetch_returns_empty_list_when_structure_intact_but_no_openings():
    client = FixtureClient({"/careers": EMPTY_LISTING_HTML})
    records = AvularCareersAdapter().fetch("https://www.avular.com", client)
    assert records == []


def test_fetch_raises_when_listing_page_structure_is_unrecognised():
    client = FixtureClient({"/careers": BROKEN_LISTING_HTML})
    with pytest.raises(AvularParseError, match="Careers"):
        AvularCareersAdapter().fetch("https://www.avular.com", client)


def test_fetch_raises_on_non_200_listing_page():
    client = FixtureClient({})  # everything 404s
    with pytest.raises(AvularParseError, match="HTTP 404"):
        AvularCareersAdapter().fetch("https://www.avular.com", client)


def test_fetch_raises_when_job_page_has_no_article_body():
    client = FixtureClient({
        "/careers": LISTING_HTML,
        "/careers/test-engineer": JOB_HTML_NO_ARTICLE_BODY,
        "/careers/office-manager": JOB_HTML_NO_ARTICLE_BODY,
    })
    with pytest.raises(AvularParseError, match="articleBody"):
        AvularCareersAdapter().fetch("https://www.avular.com", client)


def test_fetch_raises_when_metadata_line_does_not_match_known_formats():
    client = FixtureClient({
        "/careers": LISTING_HTML,
        "/careers/test-engineer": JOB_HTML_UNPARSEABLE_METADATA,
        "/careers/office-manager": JOB_HTML_UNPARSEABLE_METADATA,
    })
    with pytest.raises(AvularParseError, match="Location/Hours/Employment type"):
        AvularCareersAdapter().fetch("https://www.avular.com", client)
