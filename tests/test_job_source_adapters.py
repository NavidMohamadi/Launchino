import json
from pathlib import Path

from job_sources.ashby import AshbyAdapter
from job_sources.base import HttpResponse
from job_sources.greenhouse import GreenhouseAdapter
from job_sources.jsonld import JsonLdJobPostingAdapter
from job_sources.lever import LeverAdapter

ROOT = Path(__file__).resolve().parents[1]


class FixtureClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, *, headers=None, timeout=20.0):
        return HttpResponse(200, {"content-type": "application/json"}, json.dumps(self.payload), self.payload)


def load(name):
    return json.loads((ROOT / "data/fixtures" / name).read_text())


def test_greenhouse_adapter():
    rows = GreenhouseAdapter().fetch("exampleanalytics", FixtureClient(load("greenhouse_jobs.json")))
    assert len(rows) == 1
    assert rows[0].external_job_id == "101"
    assert rows[0].title == "Junior Supply Chain Analyst"
    assert "Analyse operational data" in rows[0].description_text


def test_lever_adapter():
    rows = LeverAdapter().fetch("examplerobotics", FixtureClient(load("lever_jobs.json")))
    assert rows[0].external_job_id == "lever-201"
    assert rows[0].employment_types == ["Full-time"]
    assert rows[0].department == "Operations Engineering"


def test_ashby_adapter():
    rows = AshbyAdapter().fetch("example", FixtureClient(load("ashby_jobs.json")))
    assert rows[0].title == "Data & Planning Trainee"
    assert rows[0].date_posted.isoformat() == "2026-07-18"


def test_jsonld_adapter():
    html = (ROOT / "data/fixtures/jobposting_page.html").read_text()
    rows = JsonLdJobPostingAdapter().parse(html=html, page_url="https://example-foods.nl/careers/sc-401")
    assert len(rows) == 1
    assert rows[0].external_job_id == "SC-401"
    assert rows[0].company_name == "Example Foods B.V."
    assert rows[0].location_text == "Tilburg, NL"
