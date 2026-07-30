"""Manual refresh mechanism for bundled reference datasets used by the
Education / Capabilities / Task History categories: ROR institutions, ESCO
skills, ESCO occupations, and DUO's Dutch higher-education program register
(the dataset that succeeded the older CROHO downloads).

Same pattern as api/job_discovery_scheduler.py: this module registers no
scheduler, cron, or background task of any kind, and nothing here ever runs
on its own. It downloads real data from each source's real public endpoint
only when explicitly invoked -- either directly:

    python -m api.reference_data_refresh --refresh ror
    python -m api.reference_data_refresh --refresh esco
    python -m api.reference_data_refresh --refresh croho
    python -m api.reference_data_refresh --refresh all

-- or via an admin clicking "Run now" on the dashboard (api/admin_tasks.py's
run_reference_refresh_task, routed through POST /admin/tasks/{task_name}/run
in api/routers/admin_tasks.py). That wrapper imports REFRESH_FUNCTIONS lazily
inside its own function body specifically so this module is still not
imported at api/main.py startup -- only the first time an admin actually
triggers a refresh.

The running application never calls any external source at request time --
it only reads the bundled files this script writes under data/reference/.

ISCED-F 2013 (education field-of-study classification) has no machine-
readable live source at all -- UNESCO publishes it only as a PDF manual --
so data/reference/isced_f_2013.json is a static, hand-transcribed bundle
with no refresh function here. It's a fixed international standard,
unchanged since 2013 and not expected to change.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx

from api import REPO_ROOT

REFERENCE_DIR = REPO_ROOT / "data" / "reference"

# A recommendation surfaced to whoever runs this script -- these are
# slow-changing reference datasets (institution registries, skills/
# occupations taxonomies, program registers), not live data. This is NOT an
# enforced schedule: nothing in this module checks it or triggers itself: it
# only prints as a reminder in --help / after each refresh.
RECOMMENDED_REFRESH_INTERVAL_DAYS = int(os.environ.get("REFERENCE_DATA_REFRESH_INTERVAL_DAYS", "30"))

ROR_ZENODO_CONCEPT_URL = "https://zenodo.org/api/records/6347574"
ESCO_SEARCH_URL = "https://ec.europa.eu/esco/api/search"
DUO_HO_PROGRAMS_CSV_URL = (
    "https://onderwijsdata.duo.nl/dataset/7c0686f4-b5c2-418e-8e44-7be0057d8084/"
    "resource/ffffa7ad-e6a2-4ba7-9fc2-a09df4128555/download/ho_opleidingsoverzicht.csv"
)

USER_AGENT = "SHEXON-Reference-Downloader/1.0 (+manual refresh, see api/reference_data_refresh.py)"


def _write_json(filename: str, payload: Dict[str, Any]) -> Path:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def refresh_ror() -> Dict[str, Any]:
    """Downloads the latest ROR (Research Organization Registry) data dump
    from Zenodo -- the concept DOI always redirects to the newest release --
    and filters to organizations whose `types` includes "education".

    This is a reasonable proxy for "university/college", not a perfect one:
    ROR doesn't catalog primary/secondary schools at all (its scope is
    research-active organizations), so "education" in practice means
    universities, colleges, and similar research-active institutions, with a
    small number of non-university educational institutes also included.
    Disclosed here rather than silently assumed exact.
    """
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        record = client.get(ROR_ZENODO_CONCEPT_URL).raise_for_status().json()
        files = record.get("files", [])
        if not files:
            raise RuntimeError("ROR Zenodo record has no files")
        zip_bytes = client.get(files[0]["links"]["self"], timeout=300).raise_for_status().content

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        json_name = next(n for n in zf.namelist() if n.endswith(".json"))
        with zf.open(json_name) as f:
            all_orgs = json.load(f)

    institutions: List[Dict[str, Any]] = []
    for org in all_orgs:
        if "education" not in org.get("types", []):
            continue
        display_name = next(
            (n["value"] for n in org.get("names", []) if "ror_display" in n.get("types", [])),
            (org.get("names") or [{}])[0].get("value", ""),
        )
        location = (org.get("locations") or [{}])[0].get("geonames_details", {})
        institutions.append({
            "ror_id": org["id"],
            "name": display_name,
            "status": org.get("status"),
            "country_code": location.get("country_code"),
            "country_name": location.get("country_name"),
        })

    path = _write_json("ror_institutions.json", {
        "source": "ROR (ror.org) via Zenodo data dump",
        "source_release_title": record.get("metadata", {}).get("title"),
        "zenodo_record_id": record.get("id"),
        "filtered_to_types": ["education"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "total_source_records": len(all_orgs),
        "count": len(institutions),
        "institutions": institutions,
    })
    return {"count": len(institutions), "total_source_records": len(all_orgs), "path": str(path)}


def _refresh_esco(concept_type: str, filename: str) -> Dict[str, Any]:
    """ESCO's `offset` query param is a PAGE INDEX, not a raw record count --
    confirmed empirically: the API's own `_links.next` href increments offset
    by 1 regardless of `limit`, and requesting offset=1&limit=5 returns
    records 5-9, not records 1-5. The real record position is
    `offset * limit`. Incrementing offset by `limit` each iteration (an easy
    mistake given how almost every other paginated API works) skips almost
    everything after the first page and silently returns a tiny, non-
    representative slice -- caught here by comparing the real record counts
    against this same script's own real run, not assumed correct because it
    exited without error."""
    results: List[Dict[str, Any]] = []
    page = 0
    limit = 100
    total = None
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        while total is None or page * limit < total:
            resp = client.get(ESCO_SEARCH_URL, params={
                "text": "", "type": concept_type, "language": "en", "limit": limit, "offset": page,
            })
            resp.raise_for_status()
            body = resp.json()
            total = body["total"]
            batch = body.get("_embedded", {}).get("results", [])
            if not batch:
                break  # safety net: stop rather than loop forever if a page is unexpectedly empty
            for r in batch:
                results.append({
                    "uri": r["uri"],
                    "code": r.get("code"),
                    "label_en": (r.get("preferredLabel") or {}).get("en", r.get("title")),
                })
            page += 1
            time.sleep(0.15)  # a reasonable citizen of a public EU government API, not a rate-limit workaround

    path = _write_json(filename, {
        "source": f"ESCO ({concept_type}s pillar) via esco.ec.europa.eu REST API",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(results),
        f"{concept_type}s": results,
    })
    return {"count": len(results), "path": str(path)}


def refresh_esco_skills() -> Dict[str, Any]:
    return _refresh_esco("skill", "esco_skills.json")


def refresh_esco_occupations() -> Dict[str, Any]:
    return _refresh_esco("occupation", "esco_occupations.json")


def refresh_croho() -> Dict[str, Any]:
    """Downloads DUO's real, current higher-education program register (the
    open dataset that succeeded the older "CROHO download" files -- see
    PROJECT_NOTES.md). Bundled as-is (CSV), same "store the source's own
    format, don't reshape it" precedent as
    data/fixtures/ind_recognised_sponsors_sample.csv."""
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        content = client.get(DUO_HO_PROGRAMS_CSV_URL).raise_for_status().content

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / "duo_ho_opleidingsoverzicht.csv"
    path.write_bytes(content)

    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    return {"count": len(rows), "path": str(path)}


REFRESH_FUNCTIONS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "ror": refresh_ror,
    "esco": lambda: {"skills": refresh_esco_skills(), "occupations": refresh_esco_occupations()},
    "croho": refresh_croho,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--refresh", choices=["ror", "esco", "croho", "all"],
        help=f"Which dataset to re-download. Recommended cadence: every {RECOMMENDED_REFRESH_INTERVAL_DAYS} days "
             "(REFERENCE_DATA_REFRESH_INTERVAL_DAYS env var) -- not automatically enforced.",
    )
    args = parser.parse_args()

    if not args.refresh:
        parser.print_help()
    else:
        targets = list(REFRESH_FUNCTIONS.keys()) if args.refresh == "all" else [args.refresh]
        for name in targets:
            print(f"Refreshing {name}...")
            result = REFRESH_FUNCTIONS[name]()
            print(f"  {name}: {result}")
