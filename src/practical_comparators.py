from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from schemas import Alignment

UNKNOWN_VALUES = {None, "unknown", "not_specified", "not_sure"}

LANGUAGE_LEVEL = {
    "basic": 1,
    "working": 2,
    "professional": 3,
    "fluent": 4,
    "native_or_equivalent": 5,
}

# Ordinal scales for score_tagged_list_overlap's two leveled use cases (CAP
# skill proficiency, EDU education level). TASK's occupation-domain matching
# is unleveled (level_order=None) -- occupations don't have a "level" the
# way a skill or a degree does.
SKILL_PROFICIENCY_LEVEL = {
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
    "expert": 4,
}

EDUCATION_LEVEL = {
    "secondary": 1,
    "vocational": 2,
    "bachelor": 3,
    "master": 4,
    "phd": 5,
    "postdoc": 6,
    # "other" is deliberately absent -- it has no defined rank, so a
    # candidate/vacancy entry at "other" always resolves UNKNOWN for the
    # leveled comparison rather than silently sorting first or last.
}


def score_sponsorship(candidate_requirement: Optional[str], vacancy_policy: Optional[str]) -> Tuple[Alignment, str]:
    if vacancy_policy in UNKNOWN_VALUES:
        return Alignment.UNKNOWN, "The vacancy does not specify sponsorship availability."
    if candidate_requirement in UNKNOWN_VALUES:
        return Alignment.UNKNOWN, "The candidate's sponsorship requirement needs clarification."
    if candidate_requirement == "not_required":
        return Alignment.ALIGNED, "The candidate does not require employer sponsorship."
    if vacancy_policy == "available":
        return Alignment.ALIGNED, "Sponsorship is required and stated as available."
    if vacancy_policy == "conditional":
        return Alignment.POTENTIALLY_ALIGNED, "Sponsorship may be available subject to stated conditions."
    if vacancy_policy == "unavailable":
        return Alignment.MISALIGNED, "The candidate requires sponsorship and the employer states it is unavailable."
    return Alignment.UNKNOWN, "Sponsorship values use an unsupported code."


def score_country_presence(candidate_presence: Optional[str], vacancy_condition: Optional[str]) -> Tuple[Alignment, str]:
    if vacancy_condition in UNKNOWN_VALUES:
        return Alignment.UNKNOWN, "The vacancy does not specify whether country presence matters."
    if candidate_presence in UNKNOWN_VALUES:
        return Alignment.UNKNOWN, "Candidate country presence needs clarification."
    if vacancy_condition == "open":
        return Alignment.ALIGNED, "The employer is open to candidates inside or outside the employment country."
    if vacancy_condition == "required":
        if candidate_presence == "in_country":
            return Alignment.ALIGNED, "The candidate is already in the employment country."
        return Alignment.MISALIGNED, "The employer requires country presence and the candidate is outside the country."
    if vacancy_condition == "preferred":
        if candidate_presence == "in_country":
            return Alignment.ALIGNED, "The candidate meets the stated country preference."
        return Alignment.WEAK_ALIGNMENT, "Country presence is preferred, not stated as required."
    return Alignment.UNKNOWN, "Country-presence values use an unsupported code."


def score_availability(
    candidate_earliest: Optional[date],
    preferred_start: Optional[date],
    latest_acceptable_start: Optional[date],
) -> Tuple[Alignment, str]:
    if preferred_start is None and latest_acceptable_start is None:
        return Alignment.UNKNOWN, "The vacancy does not specify a start window."
    if candidate_earliest is None:
        return Alignment.UNKNOWN, "Candidate availability needs clarification."
    if preferred_start is not None and candidate_earliest <= preferred_start:
        return Alignment.ALIGNED, "The candidate can start by the preferred date."
    if latest_acceptable_start is not None and candidate_earliest <= latest_acceptable_start:
        return Alignment.POTENTIALLY_ALIGNED, "The candidate can start within the latest acceptable window."
    return Alignment.MISALIGNED, "The candidate's earliest start is after the stated acceptable window."


def score_language(
    candidate_languages: Mapping[str, str],
    required_language: Optional[str],
    required_level: Optional[str],
    required_or_preferred: str = "required",
) -> Tuple[Alignment, str]:
    if required_language in UNKNOWN_VALUES or required_level in UNKNOWN_VALUES:
        return Alignment.UNKNOWN, "The vacancy does not specify a usable language requirement."
    candidate_level = candidate_languages.get(str(required_language))
    if candidate_level is None:
        return Alignment.UNKNOWN, f"No confirmed level is stored for {required_language}."
    c = LANGUAGE_LEVEL.get(candidate_level)
    r = LANGUAGE_LEVEL.get(str(required_level))
    if c is None or r is None:
        return Alignment.UNKNOWN, "Language values use an unsupported level code."
    if c >= r:
        return Alignment.ALIGNED, "The candidate meets or exceeds the stated language level."
    if required_or_preferred == "preferred":
        return Alignment.WEAK_ALIGNMENT, "The candidate is below a preferred, not required, language level."
    if r - c == 1:
        return Alignment.WEAK_ALIGNMENT, "The candidate is one level below the stated requirement."
    return Alignment.MISALIGNED, "The candidate is materially below the stated language requirement."


def score_set_compatibility(
    candidate_acceptable: Optional[Iterable[str]],
    vacancy_options: Optional[Iterable[str] | str],
    *,
    label: str,
) -> Tuple[Alignment, str]:
    if vacancy_options is None or (isinstance(vacancy_options, str) and vacancy_options in UNKNOWN_VALUES):
        return Alignment.UNKNOWN, f"The vacancy does not specify {label}."
    candidate_set = set(candidate_acceptable or [])
    if not candidate_set:
        return Alignment.UNKNOWN, f"Candidate {label} preferences need clarification."
    if isinstance(vacancy_options, str):
        vacancy_set = {vacancy_options}
    else:
        vacancy_set = set(vacancy_options or [])
    if "flexible" in vacancy_set:
        return Alignment.ALIGNED, f"The vacancy is flexible on {label}."
    overlap = candidate_set & vacancy_set
    if overlap:
        return Alignment.ALIGNED, f"Candidate and vacancy share acceptable {label}: {', '.join(sorted(overlap))}."
    return Alignment.MISALIGNED, f"Candidate and vacancy have no overlapping {label} option."


def score_work_mode(candidate_acceptable: Optional[Iterable[str]], vacancy_options) -> Tuple[Alignment, str]:
    return score_set_compatibility(candidate_acceptable, vacancy_options, label="work arrangement")


def score_contract_type(candidate_acceptable: Optional[Iterable[str]], vacancy_options) -> Tuple[Alignment, str]:
    return score_set_compatibility(candidate_acceptable, vacancy_options, label="contract type")


def score_work_type(candidate_acceptable: Optional[Iterable[str]], vacancy_options) -> Tuple[Alignment, str]:
    """PRACT-WORKTYPE (full_time/internship/student_job/part_time) -- same
    shape as score_contract_type/score_work_mode, a distinct axis from
    PRACT-CONTRACT's formal contract-type question (internship/full_time/
    traineeship/project/other)."""
    return score_set_compatibility(candidate_acceptable, vacancy_options, label="work type")


def score_tagged_list_overlap(
    candidate_entries: Optional[Iterable[Mapping[str, Any]]],
    required_entries: Optional[Iterable[Mapping[str, Any]]],
    *,
    level_order: Optional[Mapping[str, int]] = None,
    label: str,
) -> Tuple[Alignment, str]:
    """Generalizes score_language's leveled single-tag lookup (a candidate
    map checked against ONE required tag+level) and score_set_compatibility's
    overlap logic (an unleveled candidate set checked against a vacancy set)
    into one shape: does the candidate have AT LEAST ONE entry -- {"tag":
    str, "level": Optional[str]} -- that satisfies AT LEAST ONE requirement
    of the same shape, matched by overlap on "tag" and (if level_order is
    given) by an ordinal level check on "level"?

    Unleveled when level_order is None -- pure tag presence/overlap, exactly
    score_set_compatibility's rule. Leveled when level_order is given --
    score_language's exact >=required / one-below-is-weak / further-below-is-
    misaligned rule, just checked per matching tag instead of a single one.

    Each of CAP (skills, leveled by proficiency), TASK (occupation domains,
    unleveled), and EDU (level+field-as-tag, leveled by education level) maps
    its own richer entry shape into this same {"tag", "level"} pair at the
    comparator-dispatch layer before calling this -- one real implementation
    of "list of candidate entries vs required tags, matched by overlap," not
    three.
    """
    required_list = [r for r in (required_entries or []) if r.get("tag") not in UNKNOWN_VALUES]
    if not required_list:
        return Alignment.UNKNOWN, f"The vacancy does not specify required {label}."
    candidate_list = [c for c in (candidate_entries or []) if c.get("tag") not in UNKNOWN_VALUES]
    if not candidate_list:
        return Alignment.UNKNOWN, f"Candidate {label} needs clarification."

    candidate_levels_by_tag: Dict[str, List[Optional[str]]] = {}
    for c in candidate_list:
        candidate_levels_by_tag.setdefault(c["tag"], []).append(c.get("level"))

    matched_tags: List[str] = []
    any_weak = False
    for req in required_list:
        tag = req["tag"]
        candidate_levels = candidate_levels_by_tag.get(tag)
        if candidate_levels is None:
            continue
        if level_order is None:
            matched_tags.append(tag)
            continue
        r = level_order.get(str(req.get("level")))
        if r is None:
            continue
        for candidate_level in candidate_levels:
            c = level_order.get(str(candidate_level)) if candidate_level is not None else None
            if c is None:
                continue
            if c >= r:
                matched_tags.append(tag)
                break
            if r - c == 1:
                any_weak = True

    if matched_tags:
        return Alignment.ALIGNED, f"Candidate matches required {label}: {', '.join(sorted(set(matched_tags)))}."
    if any_weak:
        return Alignment.WEAK_ALIGNMENT, f"Candidate is one level below the required {label}."
    return Alignment.MISALIGNED, f"No overlap between candidate and required {label}."
