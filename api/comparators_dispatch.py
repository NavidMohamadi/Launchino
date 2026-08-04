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

from api.reference_search import esco_occupation_unit_groups
from match_engine import score_ordinal_requirement
from ordinal_comparators import score_ordinal_distance, score_ordinal_range
from practical_comparators import (
    EDUCATION_LEVEL, SKILL_PROFICIENCY_LEVEL, score_availability, score_capability_list_requirement,
    score_contract_type, score_country_presence, score_education_history, score_language,
    score_motivation_preferred_minimum, score_sponsorship, score_tagged_list_overlap, score_work_mode,
    score_work_type,
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


def score_occupation_pick(candidate_value: Dict[str, Any], vacancy_value: Dict[str, Any]) -> Tuple[Alignment, str, bool]:
    """Family 4 -- CAREER-PRIMARY-ROLE/SECONDARY-ROLE (v3 redesign, see
    PROJECT_NOTES.md): exact-or-close ESCO occupation match, not a numeric
    distance. "Close" is defined via ESCO's own ISCO-08-derived hierarchical
    code (see api/reference_search.esco_occupation_unit_groups) -- two
    occupations sharing the same unit-group prefix (e.g. "2166.3.1" and
    "2166.1") are a real, structurally-grounded "close" match, not an
    invented notion of similarity. still_exploring/open_to_adjacent soften
    an otherwise-misaligned result, since the candidate explicitly signalled
    they haven't fixed on one narrow target.
    """
    vacancy_uri = (vacancy_value.get("occupation") or {}).get("esco_uri")
    if not vacancy_uri:
        return Alignment.UNKNOWN, "The vacancy does not specify a target occupation.", True

    candidate_uri = (candidate_value.get("occupation") or {}).get("esco_uri")
    still_exploring = bool(candidate_value.get("still_exploring"))
    open_to_adjacent = bool(candidate_value.get("open_to_adjacent"))

    if not candidate_uri:
        reason = "The candidate has not confirmed a mapped ESCO occupation for this pick yet."
        if still_exploring:
            return Alignment.WEAK_ALIGNMENT, reason + " They indicated they are still exploring options.", True
        return Alignment.UNKNOWN, reason, True

    if candidate_uri == vacancy_uri:
        return Alignment.ALIGNED, "Candidate and vacancy specify the same ESCO occupation.", False

    groups = esco_occupation_unit_groups()
    candidate_group = groups.get(candidate_uri)
    same_group = candidate_group is not None and candidate_group == groups.get(vacancy_uri)
    if same_group:
        if open_to_adjacent:
            return Alignment.ALIGNED, "Different ESCO occupations, but in the same broad group; candidate is open to adjacent roles.", False
        return Alignment.WEAK_ALIGNMENT, "Candidate and vacancy occupations sit in the same broad ESCO occupational group.", True

    if open_to_adjacent or still_exploring:
        return Alignment.WEAK_ALIGNMENT, "No occupation-group overlap, but the candidate indicated openness to adjacent roles.", True

    return Alignment.MISALIGNED, "No overlap between the candidate's and vacancy's target occupations.", False


def score_industry_overlap(candidate_value: Dict[str, Any], vacancy_value: Dict[str, Any]) -> Tuple[Alignment, str]:
    """Family 4 -- CAREER-INDUSTRIES (v3 redesign, see PROJECT_NOTES.md): NACE
    is mapped at section level only in this system (21 sections, no
    sub-hierarchy -- see data/reference/nace_industries.json), so "close"
    reduces to plain set overlap, exactly score_tagged_list_overlap's
    existing unleveled semantics (same primitive TASK-EXPERIENCE's
    occupation-domain matching already uses)."""
    candidate_entries = [
        {"tag": i.get("nace_code") or i.get("raw_text")}
        for i in (candidate_value.get("industries") or [])
        if isinstance(i, dict) and (i.get("nace_code") or i.get("raw_text"))
    ]
    required_entries = [
        {"tag": i.get("nace_code")}
        for i in (vacancy_value.get("industries") or [])
        if isinstance(i, dict) and i.get("nace_code")
    ]
    return score_tagged_list_overlap(candidate_entries, required_entries, level_order=None, label="industries")


def compare_answered_values(
    element: FitElement, candidate_value: Dict[str, Any], vacancy_value: Dict[str, Any]
) -> Tuple[Alignment, str, bool, Optional[float]]:
    """Return (alignment, reason, clarification_required, score_percent) for
    an ANSWERED item. score_percent (v3 redesign, see PROJECT_NOTES.md) is
    None for every pre-existing discrete-only comparator (make_item_result
    then derives score from ALIGNMENT_SCORE[alignment] exactly as before);
    Family 1/2/3's continuous formulas are the only branches that provide a
    real 0-100 value here."""
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
        return cmp.alignment, cmp.reason, cmp.clarification_required, None

    if key == "ordinal_distance":
        # Family 2 (v3 redesign): new single-value ENV-*/RIASEC elements.
        alignment, reason, percent = score_ordinal_distance(
            candidate_value.get("level"), vacancy_value.get("required_level")
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, percent

    if key == "ordinal_requirement":
        # Family 1 (v3 redesign): 6 TEAM capability elements + TASK-YEARS.
        alignment, reason, percent = score_ordinal_requirement(
            candidate_value.get("level"), vacancy_value.get("required_level")
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, percent

    if key == "motivation_preferred_minimum":
        # Family 3 (v3 redesign): MOT-CHALLENGE (13th MOT element, born
        # directly in the new preferred+minimum shape -- see PROJECT_NOTES.md).
        alignment, reason, percent = score_motivation_preferred_minimum(candidate_value, vacancy_value)
        return alignment, reason, alignment == Alignment.UNKNOWN, percent

    if key == "visa_sponsorship":
        alignment, reason = score_sponsorship(candidate_value.get("requirement"), vacancy_value.get("policy"))
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "country_presence":
        alignment, reason = score_country_presence(
            candidate_value.get("presence_relative_to_vacancy"), vacancy_value.get("condition")
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "availability":
        alignment, reason = score_availability(
            _parse_date(candidate_value.get("earliest_start")),
            _parse_date(vacancy_value.get("preferred_start")),
            _parse_date(vacancy_value.get("latest_acceptable_start")),
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "language_level":
        alignment, reason = score_language(
            candidate_value.get("languages", {}),
            vacancy_value.get("language"),
            vacancy_value.get("minimum_level"),
            vacancy_value.get("status", "required"),
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "contract_set":
        alignment, reason = score_contract_type(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "work_mode_set":
        alignment, reason = score_work_mode(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "work_type_set":
        alignment, reason = score_work_type(
            candidate_value.get("acceptable"), _extract_offered(vacancy_value.get("description"))
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "semantic_overlap":
        alignment, reason, clarification_required = score_semantic_overlap(
            candidate_value.get("values"), vacancy_value.get("values")
        )
        return alignment, reason, clarification_required, None

    if key == "tagged_list_overlap_skills":
        # CAP-SKILLS Family 1 (v3 redesign): repeatable {skill, level,
        # esco_uri, confidence} entries, leveled by proficiency, continuous
        # shortfall percent rather than a discrete bucket.
        candidate_entries = _tags_from_entries(
            candidate_value.get("skills"), code_field="esco_uri", text_field="skill", level_field="level",
        )
        required_entries = _tags_from_entries(
            vacancy_value.get("required_skills"), code_field="esco_uri", text_field="skill", level_field="level",
        )
        alignment, reason, percent = score_capability_list_requirement(
            candidate_entries, required_entries, level_order=SKILL_PROFICIENCY_LEVEL, label="skills",
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, percent

    if key == "tagged_list_overlap_occupation":
        # TASK-EXPERIENCE: repeatable {job_title, esco_uri, confidence,
        # start_date, end_date} entries, unleveled (occupation-domain
        # presence/overlap only -- years of experience is TASK-YEARS'
        # separate ordinal_requirement element, not this one). Family 4
        # (categorical, not a numeric distance) -- discrete alignment only,
        # same as CAREER's ESCO/NACE picks below.
        candidate_entries = _tags_from_entries(
            candidate_value.get("jobs"), code_field="esco_uri", text_field="job_title",
        )
        required_entries = _tags_from_entries(
            vacancy_value.get("required_occupations"), code_field="esco_uri", text_field="occupation",
        )
        alignment, reason = score_tagged_list_overlap(
            candidate_entries, required_entries, level_order=None, label="occupation experience",
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    if key == "tagged_list_overlap_education":
        # EDU-HISTORY Family 1 (v3 redesign): level is always a continuous
        # shortfall percent; how a field mismatch affects that score depends
        # on the vacancy's education_field_requirement (required/preferred/
        # open -- see score_education_history). Only entries with
        # consider != False are eligible; best (entry x requirement) pair wins.
        alignment, reason, percent = score_education_history(
            candidate_value.get("entries"),
            vacancy_value.get("required_education"),
            field_requirement=vacancy_value.get("education_field_requirement", "open"),
        )
        return alignment, reason, alignment == Alignment.UNKNOWN, percent

    if key == "esco_occupation_pick":
        alignment, reason, clarification_required = score_occupation_pick(candidate_value, vacancy_value)
        return alignment, reason, clarification_required, None

    if key == "nace_industry_overlap":
        alignment, reason = score_industry_overlap(candidate_value, vacancy_value)
        return alignment, reason, alignment == Alignment.UNKNOWN, None

    raise ValueError(f"Unsupported comparator_key: {key}")
