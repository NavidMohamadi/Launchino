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
    EDUCATION_LEVEL, SKILL_PROFICIENCY_LEVEL, score_availability, score_contract_type, score_country_presence,
    score_language, score_sponsorship, score_tagged_list_overlap, score_work_mode, score_work_type,
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


def _tags_from_entries(entries: Any, *, code_field: str, text_field: str, level_field: Optional[str] = None) -> list:
    """Maps a list of repeatable CAP/TASK/EDU entries into the plain
    {"tag": ..., "level": ...} shape score_tagged_list_overlap expects. The
    mapped standard code (ESCO/ISCED) is the stable join key when present;
    an entry with no mapping yet (or a mapping the candidate hasn't
    confirmed) falls back to its own raw free-text field, so an unmapped
    entry still gets literal-text comparability rather than being silently
    excluded from matching entirely."""
    if not isinstance(entries, list):
        return []
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tag = entry.get(code_field) or entry.get(text_field)
        if not tag:
            continue
        result.append({"tag": tag, "level": entry.get(level_field) if level_field else None})
    return result


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

    if key == "work_type_set":
        alignment, reason = score_work_type(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "semantic_overlap":
        return score_semantic_overlap(candidate_value.get("values"), vacancy_value.get("values"))

    if key == "tagged_list_overlap_skills":
        # CAP-SKILLS: repeatable {skill, level, esco_uri, confidence} entries,
        # leveled by proficiency. Phase 5 (vacancy-side required skills) has
        # not shipped yet, so vacancy_value["required_skills"] is always
        # empty today -- correctly resolves UNKNOWN, not a guessed match.
        candidate_entries = _tags_from_entries(
            candidate_value.get("skills"), code_field="esco_uri", text_field="skill", level_field="level",
        )
        required_entries = _tags_from_entries(
            vacancy_value.get("required_skills"), code_field="esco_uri", text_field="skill", level_field="level",
        )
        alignment, reason = score_tagged_list_overlap(
            candidate_entries, required_entries, level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "tagged_list_overlap_occupation":
        # TASK-EXPERIENCE: repeatable {job_title, esco_uri, confidence,
        # start_date, end_date} entries, unleveled (occupation-domain
        # presence/overlap only -- years of experience is TASK-YEARS'
        # separate ordinal_requirement element, not this one).
        candidate_entries = _tags_from_entries(
            candidate_value.get("jobs"), code_field="esco_uri", text_field="job_title",
        )
        required_entries = _tags_from_entries(
            vacancy_value.get("required_occupations"), code_field="esco_uri", text_field="occupation",
        )
        alignment, reason = score_tagged_list_overlap(
            candidate_entries, required_entries, level_order=None, label="occupation experience",
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    if key == "tagged_list_overlap_education":
        # EDU-HISTORY: repeatable {level, institution, program, field:
        # {isced_code, confidence}, start_date, end_date, status} entries.
        # "tag" is the mapped ISCED-F field code (falling back to the raw
        # program text if unmapped); "level" is the education level
        # (secondary/vocational/bachelor/master/phd).
        candidate_entries = [
            {"tag": (e.get("field") or {}).get("isced_code") or e.get("program"), "level": e.get("level")}
            for e in (candidate_value.get("entries") or []) if isinstance(e, dict)
            and ((e.get("field") or {}).get("isced_code") or e.get("program"))
        ]
        required_entries = [
            {"tag": r.get("isced_code") or r.get("field"), "level": r.get("level")}
            for r in (vacancy_value.get("required_education") or []) if isinstance(r, dict)
            and (r.get("isced_code") or r.get("field"))
        ]
        alignment, reason = score_tagged_list_overlap(
            candidate_entries, required_entries, level_order=EDUCATION_LEVEL, label="education",
        )
        return alignment, reason, alignment == Alignment.UNKNOWN

    raise ValueError(f"Unsupported comparator_key: {key}")
