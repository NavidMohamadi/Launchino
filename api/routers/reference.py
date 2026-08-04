"""Reference-data search: institution/programme autocomplete for the
Education survey page (Phase 4), and ESCO skill/occupation search + ISCED-F
field listing for the vacancy-side required-skills/occupations/education
pickers (Phase 5 -- see PROJECT_NOTES.md). Read-only, in-memory lookups
against api/reference_data_refresh.py's bundled datasets -- no external
calls, no database.

Open to candidates AND companies: institutions/programs are only ever used
candidate-side today, but there is no real reason to gate them company-side
(read-only, no PII, no cost) -- simpler to allow the whole router uniformly
than to split auth per-endpoint for no real benefit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api import reference_search
from api.auth import require_role

router = APIRouter(
    prefix="/reference", tags=["reference"], dependencies=[Depends(require_role("candidate", "company", "admin"))],
)


@router.get("/institutions")
def get_institutions(q: str = Query(min_length=1, max_length=200)) -> list:
    return reference_search.search_institutions(q)


@router.get("/programs")
def get_programs(q: str = Query(min_length=1, max_length=200)) -> list:
    return reference_search.search_programs(q)


@router.get("/skills")
def get_skills(q: str = Query(min_length=1, max_length=200)) -> list:
    return reference_search.search_skills(q)


@router.get("/occupations")
def get_occupations(q: str = Query(min_length=1, max_length=200)) -> list:
    return reference_search.search_occupations(q)


@router.get("/isced-fields")
def get_isced_fields() -> list:
    return reference_search.list_isced_fields()


@router.get("/nace-sections")
def get_nace_sections() -> list:
    # v3 redesign, Phase 5 (see PROJECT_NOTES.md): CAREER-INDUSTRIES' picker --
    # full fixed list, not a search, same reasoning as isced-fields above (only
    # 21 NACE sections, small enough to browse/pick directly).
    return reference_search.list_nace_sections()
