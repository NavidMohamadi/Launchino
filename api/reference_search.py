"""Search/listing over the reference datasets api/reference_data_refresh.py
(Phase 0) bundles under data/reference/ -- institutions/programmes (Phase 4,
candidate-facing Education autocomplete) and ESCO skills/occupations plus
ISCED-F fields (Phase 5, vacancy-facing required-skills/occupations/education
pickers, see PROJECT_NOTES.md). Read-only, in-memory, no external calls at
request time -- same "offline refresh, online read" separation as that
module. The ESCO/ISCED loaders here are also reused by
api/mapping_service.py's AI mapping (candidate side) -- one real loading
implementation, not two.

Institution search backs institution.ror_id/name (candidate picks a real ROR
institution, or falls back to a free-text "other" the frontend handles
itself -- this module never invents a ror_id for an unmatched name).
Programme search backs the programme-name autocomplete for Dutch higher-ed
programmes (DUO's registry); ISCED-F field mapping for whatever programme
name is ultimately chosen (autocompleted or free-text) is a separate concern
handled by api/mapping_service.py's map_program_to_isced -- this module only
helps a candidate find/confirm the programme's official name, it does not
classify it.

Skill/occupation search backs a company's required-skills/required-occupations
pickers directly (search-and-pick a real ESCO code) -- deliberately NOT
routed through the AI mapping service the way candidate self-reported skills
are: a company is authoritatively DEFINING a requirement, not self-reporting
an ambiguous personal fact, so picking an exact ESCO code directly is more
appropriate (and cheaper) than an AI-guessed mapping with a confidence score.
ISCED-F fields are listed in full (only 29 narrow fields, small enough) for
the same reason -- a company picks the required field of study directly
rather than naming a specific programme to have classified.
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from typing import Any, Dict, List

from api import REPO_ROOT
from api.text_search import shortlist_by_text_similarity

REFERENCE_DIR = REPO_ROOT / "data" / "reference"
SEARCH_LIMIT = 20


@lru_cache(maxsize=1)
def load_institutions() -> List[Dict[str, Any]]:
    data = json.loads((REFERENCE_DIR / "ror_institutions.json").read_text(encoding="utf-8"))
    # "active" only -- a withdrawn/inactive institution isn't a real pick for
    # a current or prospective student to select.
    return [
        {"ror_id": i["ror_id"], "name": i["name"], "country_name": i.get("country_name")}
        for i in data["institutions"] if i.get("status") == "active"
    ]


@lru_cache(maxsize=1)
def load_programs() -> List[Dict[str, Any]]:
    # Deduplicated by programme name: the DUO registry has one row per
    # institution offering a programme (6,807 rows), but a candidate is
    # picking a programme NAME/level here, not a specific institution's
    # specific offering -- that's the separate institution.name/ror_id
    # field. International name preferred over the Dutch name when present.
    path = REFERENCE_DIR / "duo_ho_opleidingsoverzicht.csv"
    seen: Dict[str, Dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=","):
            name = (row.get("INTERNATIONALE_NAAM") or row.get("NAAM_LANG") or "").strip()
            if not name or name in seen:
                continue
            seen[name] = {"name": name, "level": row.get("NIVEAU")}
    return list(seen.values())


@lru_cache(maxsize=1)
def load_esco_skills() -> List[Dict[str, Any]]:
    data = json.loads((REFERENCE_DIR / "esco_skills.json").read_text(encoding="utf-8"))
    return [{"uri": s["uri"], "label": s["label_en"]} for s in data["skills"] if s.get("label_en")]


@lru_cache(maxsize=1)
def load_esco_occupations() -> List[Dict[str, Any]]:
    data = json.loads((REFERENCE_DIR / "esco_occupations.json").read_text(encoding="utf-8"))
    return [{"uri": o["uri"], "label": o["label_en"]} for o in data["occupations"] if o.get("label_en")]


@lru_cache(maxsize=1)
def load_isced_narrow_fields() -> List[Dict[str, Any]]:
    data = json.loads((REFERENCE_DIR / "isced_f_2013.json").read_text(encoding="utf-8"))
    return [{"code": f["code"], "label": f["name"]} for f in data["narrow_fields"]]


def search_institutions(query: str) -> List[Dict[str, Any]]:
    return shortlist_by_text_similarity(query, load_institutions(), label_field="name", limit=SEARCH_LIMIT)


def search_programs(query: str) -> List[Dict[str, Any]]:
    return shortlist_by_text_similarity(query, load_programs(), label_field="name", limit=SEARCH_LIMIT)


def search_skills(query: str) -> List[Dict[str, Any]]:
    return shortlist_by_text_similarity(query, load_esco_skills(), label_field="label", limit=SEARCH_LIMIT)


def search_occupations(query: str) -> List[Dict[str, Any]]:
    return shortlist_by_text_similarity(query, load_esco_occupations(), label_field="label", limit=SEARCH_LIMIT)


def list_isced_fields() -> List[Dict[str, Any]]:
    # Full list, not a search -- only 29 entries, small enough for a company
    # to pick from directly (see module docstring).
    return load_isced_narrow_fields()
