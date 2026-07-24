"""Maps a Fit Dictionary element's comparator_key to the right src/ comparator.

Every branch below calls unmodified functions from src/ordinal_comparators.py,
src/practical_comparators.py or src/match_engine.py. The one exception is
CAREER's "semantic_overlap" key, which src/ does not implement (the blueprint
treats free-text role-direction overlap as an AI-assisted judgement, see
prompts/P06_item_comparison.txt). score_semantic_overlap() below is a
deterministic, exact-text-match placeholder so the endpoint stays usable
without an AI call; it always requests clarification because it cannot
establish true semantic similarity.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple

from match_engine import score_ordinal_requirement
from ordinal_comparators import score_ordinal_range
from practical_comparators import (
    score_availability, score_contract_type, score_country_presence,
    score_language, score_sponsorship, score_work_mode,
)
from schemas import Alignment, FitElement, OrdinalRange


def _parse_date(value: Any) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _extract_offered(description: Any) -> Any:
    """PRACT-CONTRACT / PRACT-WORKMODE store {"offered": [...]} or "not_specified"."""
    if isinstance(description, dict):
        return description.get("offered")
    return description


def score_semantic_overlap(candidate_values: Any, vacancy_values: Any) -> Tuple[Alignment, str, bool]:
    vacancy_set = {str(v).strip().casefold() for v in (vacancy_values or []) if str(v).strip()}
    candidate_set = {str(v).strip().casefold() for v in (candidate_values or []) if str(v).strip()}
    if not vacancy_set:
        return Alignment.UNKNOWN, "The vacancy does not specify comparable role-direction text.", True
    if not candidate_set:
        return Alignment.UNKNOWN, "The candidate has not specified comparable role-direction text.", True
    overlap = candidate_set & vacancy_set
    if overlap:
        return (
            Alignment.ALIGNED,
            f"Exact-text overlap found ({', '.join(sorted(overlap))}); confirm with a human/AI semantic review.",
            True,
        )
    return (
        Alignment.WEAK_ALIGNMENT,
        "No exact-text overlap; this deterministic placeholder cannot judge semantic similarity "
        "and this item requires AI-assisted or human review (see prompts/P06_item_comparison.txt).",
        True,
    )


def compare_answered_values(
    element: FitElement, candidate_value: Dict[str, Any], vacancy_value: Dict[str, Any]
) -> Tuple[Alignment, str, bool]:
    """Return (alignment, reason, clarification_required) for an ANSWERED item."""
    key = element.comparator_key

    if key == "ordinal_range":
        try:
            candidate_range = OrdinalRange(
                preferred_min=candidate_value["preferred_min"],
                preferred_max=candidate_value["preferred_max"],
                tolerable_min=candidate_value["tolerable_min"],
                tolerable_max=candidate_value["tolerable_max"],
            )
        except (KeyError, TypeError, ValueError):
            candidate_range = None
        vacancy_actual = vacancy_value.get("actual")
        vacancy_actual = vacancy_actual if isinstance(vacancy_actual, int) else None
        cmp = score_ordinal_range(candidate_range, vacancy_actual)
        return cmp.alignment, cmp.reason, cmp.clarification_required

    if key == "ordinal_requirement":
        alignment, reason = score_ordinal_requirement(
            candidate_value.get("level"), vacancy_value.get("required_level")
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "visa_sponsorship":
        alignment, reason = score_sponsorship(candidate_value.get("requirement"), vacancy_value.get("policy"))
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "country_presence":
        alignment, reason = score_country_presence(
            candidate_value.get("presence_relative_to_vacancy"), vacancy_value.get("condition")
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "availability":
        alignment, reason = score_availability(
            _parse_date(candidate_value.get("earliest_start")),
            _parse_date(vacancy_value.get("preferred_start")),
            _parse_date(vacancy_value.get("latest_acceptable_start")),
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "language_level":
        alignment, reason = score_language(
            candidate_value.get("languages", {}),
            vacancy_value.get("language"),
            vacancy_value.get("minimum_level"),
            vacancy_value.get("status", "required"),
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "contract_set":
        alignment, reason = score_contract_type(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "work_mode_set":
        alignment, reason = score_work_mode(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "semantic_overlap":
        return score_semantic_overlap(candidate_value.get("values"), vacancy_value.get("values"))

    raise ValueError(f"Unsupported comparator_key: {key}")
