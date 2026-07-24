"""Read-only Fit Dictionary access for frontend/ form rendering.

The frontend needs to know (a) what questions exist and (b) which of them
are currently active, without duplicating src/activation.py's activation
rules in JavaScript. This calls activation.is_activated() directly, unmodified
-- it does not implement any activation policy itself.

candidate_selected_ids / vacancy_activated_ids let the frontend ask "given
these selections so far (e.g. the 5 MOT factors a candidate ranked, or the
TEAM behaviours a hiring manager prioritised), what's active now" -- the
same activation resolution matching_service.build_item_results makes at
match time, but usable before any answers exist, purely for rendering.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection

from activation import is_activated

from api.database import get_connection
from api.matching_service import load_dictionary

router = APIRouter(prefix="/fit-dictionary", tags=["fit-dictionary"])


def _parse_ids(raw: Optional[str]) -> set:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


@router.get("")
def list_fit_dictionary(
    candidate_selected_ids: Optional[str] = Query(default=None, description="Comma-separated element_ids the candidate has selected (e.g. top-5 MOT ranking)."),
    vacancy_activated_ids: Optional[str] = Query(default=None, description="Comma-separated element_ids the vacancy has activated (e.g. prioritised TEAM behaviours, activated CAP/TASK)."),
    conn: Connection = Depends(get_connection),
) -> List[dict]:
    selected = _parse_ids(candidate_selected_ids)
    activated = _parse_ids(vacancy_activated_ids)
    dictionary = load_dictionary(conn)

    results = []
    for element in dictionary.values():
        active = is_activated(
            element,
            candidate_selected=element.element_id in selected,
            vacancy_activated=element.element_id in activated,
        )
        results.append({
            "element_id": element.element_id,
            "category": element.category.value,
            "label": element.label,
            "definition": element.definition,
            "activation_policy": element.activation_policy.value,
            "candidate_question": element.candidate_question,
            "vacancy_question": element.vacancy_question,
            "candidate_value_schema": element.candidate_value_schema,
            "vacancy_value_schema": element.vacancy_value_schema,
            "comparator_key": element.comparator_key,
            "sharing_status": element.sharing_status.value,
            "active": active,
        })
    return results
