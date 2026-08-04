"""AI mapping service: free-text skill / job title / study programme ->
external taxonomy code (ESCO skill, ESCO occupation, ISCED-F 2013 field),
with a confidence score.

Backs CAP-SKILLS.skills[].esco_uri, TASK-EXPERIENCE.jobs[].esco_uri, and
EDU-HISTORY.entries[].field.isced_code (see data/fit_dictionary_starter.json
and PROJECT_NOTES.md's Phase 2 entry) -- these are candidate self-reported
skills/jobs/programmes, AI-mapped to a code for matching purposes, not a
separate Fit Dictionary taxonomy-governance concern (that is
src/normalisation_registry.py / prompts/P03_element_normalisation.txt, whose
own one-element-per-skill premise is obsolete for CAP/TASK since the Phase 1
redesign made them single repeatable-array elements -- see PROJECT_NOTES.md).

Two-stage design, same reasoning as api/extraction_service.py's own
"embed the value_schema" fix: ESCO has 13,485 skills and 2,942 occupations,
far too many to hand Claude in one prompt, so a cheap local text-similarity
pre-filter (reusing vacancy_utils.normalise_text + difflib, the same
mechanism src/ind_sponsor_registry.py's SponsorRegistry.lookup() already
uses for company-name fuzzy matching) narrows each call to a shortlist of
candidates; Claude then makes the real semantic judgement plus a confidence
score from that shortlist. ISCED-F 2013 has only 29 narrow fields, small
enough to send in full -- no shortlist stage for programme mapping.

requires_confirmation on the returned MappingResult mirrors
CompanySponsorshipSignal.human_review_required (same file, same "never
silently accept uncertain AI output" shape): true whenever nothing matched,
or confidence is below MAPPING_CONFIDENCE_THRESHOLD. The caller (the
candidate, via the survey UI) must confirm or correct the mapping before it
is treated as settled.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from mapping_schemas import MappingResponse, MappingResult

from api import REPO_ROOT, ai_client
from api.reference_search import load_esco_occupations, load_esco_skills, load_isced_narrow_fields, load_nace_sections
from api.text_search import shortlist_by_text_similarity

# Below this confidence, or when nothing matched at all, the candidate must
# confirm or correct the mapping before it's treated as settled -- see the
# module docstring. A plain env-var-overridable constant, not hardcoded,
# matching api/reference_data_refresh.py's RECOMMENDED_REFRESH_INTERVAL_DAYS
# precedent for "tunable value, not a magic number buried in code."
MAPPING_CONFIDENCE_THRESHOLD = float(os.environ.get("MAPPING_CONFIDENCE_THRESHOLD", "0.7"))

SHORTLIST_SIZE = 20

TOOL_OUTPUT_INSTRUCTIONS = (
    "Return your answer only by calling the submit_mapping tool with arguments "
    "matching its input schema exactly. Do not include any other text or commentary."
)


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def _load_prompt(filename: str) -> str:
    return (REPO_ROOT / "prompts" / filename).read_text(encoding="utf-8")


def _to_result(response: MappingResponse, *, valid_codes: Optional[set] = None) -> MappingResult:
    # Real-API testing (see PROJECT_NOTES.md) found Claude reporting high
    # confidence for a shortlist item its own reasoning admitted was not a
    # genuine match ("Excel" -> "KDevelop" at confidence 0.9, reasoning:
    # "not a perfect semantic match") -- self-reported confidence alone is
    # not trustworthy. valid_codes is a hard, code-level backstop: if Claude
    # returns a code that was never in the list it was given (invention) it
    # is discarded outright, regardless of confidence. This does not fully
    # solve the Excel case above (KDevelop genuinely was in the shortlist),
    # which is addressed by the prompt's tightened confidence-calibration
    # rules instead -- this check only catches outright invention.
    matched_code = response.matched_code
    matched_label = response.matched_label
    confidence = response.confidence
    if matched_code is not None and valid_codes is not None and matched_code not in valid_codes:
        matched_code, matched_label, confidence = None, None, 0.0
    requires_confirmation = (matched_code is None) or confidence < MAPPING_CONFIDENCE_THRESHOLD
    return MappingResult(
        matched_code=matched_code, matched_label=matched_label,
        confidence=confidence, requires_confirmation=requires_confirmation,
        reasoning=response.reasoning,
    )


def _run_shortlist_mapping(
    *, raw_term: str, options: List[Dict[str, Any]], prompt_file: str, task: str, candidate_id: Optional[str],
) -> MappingResult:
    shortlist = shortlist_by_text_similarity(raw_term, options, limit=SHORTLIST_SIZE)
    if not shortlist:
        return MappingResult(
            matched_code=None, matched_label=None, confidence=0.0, requires_confirmation=True,
            reasoning="No reference entry is even a rough text match for this term.",
        )
    user = _fill(_load_prompt(prompt_file), RAW_TERM=raw_term, SHORTLIST_JSON=json.dumps(shortlist))
    user += f"\n\n{TOOL_OUTPUT_INSTRUCTIONS}"
    response = ai_client.call_claude_structured(
        model=ai_client.MODEL_FOR_TASK[task], system="You are the SHEXON taxonomy-mapping assistant described below.",
        user=user, response_model=MappingResponse, task=task, candidate_id=candidate_id,
    )
    return _to_result(response, valid_codes={item["uri"] for item in shortlist})


def map_skill_to_esco(raw_term: str, *, candidate_id: Optional[str] = None) -> MappingResult:
    return _run_shortlist_mapping(
        raw_term=raw_term, options=load_esco_skills(), prompt_file="P22_skill_esco_mapping.txt",
        task="skill_mapping", candidate_id=candidate_id,
    )


def map_occupation_to_esco(raw_term: str, *, candidate_id: Optional[str] = None) -> MappingResult:
    return _run_shortlist_mapping(
        raw_term=raw_term, options=load_esco_occupations(), prompt_file="P23_occupation_esco_mapping.txt",
        task="occupation_mapping", candidate_id=candidate_id,
    )


def map_program_to_isced(raw_term: str, *, candidate_id: Optional[str] = None) -> MappingResult:
    fields = load_isced_narrow_fields()
    user = _fill(
        _load_prompt("P24_program_isced_mapping.txt"), RAW_TERM=raw_term, ISCED_FIELDS_JSON=json.dumps(fields),
    )
    user += f"\n\n{TOOL_OUTPUT_INSTRUCTIONS}"
    response = ai_client.call_claude_structured(
        model=ai_client.MODEL_FOR_TASK["program_mapping"],
        system="You are the SHEXON taxonomy-mapping assistant described below.",
        user=user, response_model=MappingResponse, task="program_mapping", candidate_id=candidate_id,
    )
    return _to_result(response, valid_codes={item["code"] for item in fields})


def map_industry_to_nace(raw_term: str, *, candidate_id: Optional[str] = None) -> MappingResult:
    # Same "full fixed list, no shortlist stage" shape as map_program_to_isced
    # -- only 21 NACE sections, small enough to send in full (see
    # data/reference/nace_industries.json).
    sections = load_nace_sections()
    user = _fill(
        _load_prompt("P25_industry_nace_mapping.txt"), RAW_TERM=raw_term, NACE_SECTIONS_JSON=json.dumps(sections),
    )
    user += f"\n\n{TOOL_OUTPUT_INSTRUCTIONS}"
    response = ai_client.call_claude_structured(
        model=ai_client.MODEL_FOR_TASK["industry_mapping"],
        system="You are the SHEXON taxonomy-mapping assistant described below.",
        user=user, response_model=MappingResponse, task="industry_mapping", candidate_id=candidate_id,
    )
    return _to_result(response, valid_codes={item["code"] for item in sections})
