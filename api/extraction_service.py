"""Fills prompts/P01 and prompts/P04 and runs them through Claude.

The prompt files' own OUTPUT JSON blocks are a looser draft shape than the
Pydantic contracts we actually validate against (CandidateExtractionResult /
VacancyExtractionResult, which nest a real TalentElementValue /
VacancyElementValue so a human can carry the result straight into
POST /candidates/{id}/survey or POST /vacancies/{id}/workshop with minimal
editing). The prompt text still supplies the extraction task, guardrails and
inputs; the appended tool-output instructions below tell Claude which schema
and which fixed field values (talent_id/vacancy_id/source_type, and for
vacancies the placeholder source_url/source_snapshot_id a manually pasted
description doesn't have) to use instead.

VacancyExtractionResult must never be passed to src/vacancy_extraction.py's
apply_extraction_result(). That function is for the real scraping/ingestion
pipeline, where source_url/source_snapshot_id are genuine per-field
provenance; here they're the fixed "shexon://vacancy-description-extraction"
sentinel (matching the same fictional-URI convention src/company_intake.py
already uses for company-direct submissions with no real URL), because this
whole endpoint's design already routes confirmed data through
POST /vacancies/{id}/workshop instead, which stamps it verification_status
company_validated regardless of what drafted it (see api/routers/vacancies.py).
Feeding the sentinel into apply_extraction_result would create a fake-looking
low-trust "source" in vacancy_field_provenance and dilute a real vacancy's
trust ranking.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from api import REPO_ROOT, ai_client
from candidate_extraction import CandidateExtractionResult
from schemas import Category, FitElement
from vacancy_extraction import VacancyExtractionResult

PROMPTS_DIR = REPO_ROOT / "prompts"
MAPPING_MEMORY_PATH = REPO_ROOT / "data" / "mapping_memory.json"

# CV extraction is scoped to Basic Info (handled separately, see
# CandidateExtractionResult.basic_info) + these two Fit Dictionary
# categories only (Phase 3 of Education/Capabilities/Task History -- see
# PROJECT_NOTES.md). CAP/TASK are deliberately excluded: a CV extraction can
# only ever produce a low-confidence guess at a skill/job-title-to-ESCO
# mapping, and Phase 1/2 already built a real, purpose-built path for that
# (api/mapping_service.py, driven by explicit candidate entry) -- letting CV
# extraction attempt the same thing via a completely different, less
# reliable route would give two silently-diverging ways to fill the same
# data. CAREER/MOT/ENV/TEAM are excluded because a CV is a record of what
# someone did, not a survey of preferences/motivations it could ever
# honestly answer. This is a hard code-level allowlist, not a side effect of
# which elements happen to be active=true -- it must keep excluding CAP/TASK
# even after Phase 4 flips their active flag to make them real for manual
# entry.
CV_EXTRACTION_CATEGORIES = {Category.PRACT, Category.EDU}


def _scope_to_cv_extraction_categories(dictionary: Dict[str, FitElement]) -> Dict[str, FitElement]:
    return {element_id: element for element_id, element in dictionary.items() if element.category in CV_EXTRACTION_CATEGORIES}


# Vacancy-description extraction is scoped to exclude EDU/CAP/TASK (Phase 5
# of Education/Capabilities/Task History -- see PROJECT_NOTES.md), the exact
# same reasoning CV_EXTRACTION_CATEGORIES above already applies candidate-side:
# a vacancy-description extraction can only ever produce a low-confidence
# guess at a required-skill/occupation/field-of-study-to-ESCO/ISCED-F
# mapping, and Phase 5 already built a real, purpose-built path for that --
# a company directly searches and picks an exact ESCO/ISCED-F code (see
# frontend/src/components/RequirementListEditor.jsx), rather than getting an
# AI's best-guess code inline with no confidence check at all (unlike the
# candidate-side AI mapping, which at least has api/mapping_service.py's own
# confidence/requires_confirmation gate -- vacancy extraction has no
# equivalent gate today, so silently accepting an inline-guessed code here
# would be strictly worse than the candidate-side case Phase 3 already fixed).
# PRACT/TEAM/CAREER/MOT/ENV keep their existing behavior unchanged -- there is
# no equivalent dedicated manual-entry alternative for those, so vacancy
# extraction remains the real, useful path for them.
VACANCY_EXTRACTION_EXCLUDED_CATEGORIES = {Category.EDU, Category.CAP, Category.TASK}


def _scope_to_vacancy_extraction_categories(dictionary: Dict[str, FitElement]) -> Dict[str, FitElement]:
    return {
        element_id: element for element_id, element in dictionary.items()
        if element.category not in VACANCY_EXTRACTION_EXCLUDED_CATEGORIES
    }

TOOL_OUTPUT_INSTRUCTIONS = (
    "Return your answer only by calling the submit_extraction tool with arguments "
    "matching its input schema exactly. Do not include any other text or commentary."
)


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _dictionary_summary(dictionary: Dict[str, FitElement], *, schema_field: str) -> List[dict]:
    # schema_field is "candidate_value_schema" or "vacancy_value_schema" -- whichever side
    # this prompt is extracting for. Earlier versions of this summary sent only
    # element_id/category/label, giving the model no way to know each element's actual
    # value shape; it had to guess key names from the label text alone, which produced
    # answers that passed TalentElementValue/VacancyElementValue's schema validation
    # (value is just Dict[str, Any]) but used non-canonical keys the comparators and
    # review-screen editors don't recognize. See VALUE_SCHEMA rule below.
    return [
        {
            "element_id": e.element_id, "category": e.category.value, "label": e.label,
            "value_schema": getattr(e, schema_field),
        }
        for e in dictionary.values()
    ]


def _mapping_memory(dictionary: Dict[str, FitElement]) -> List[dict]:
    # Filtered to entries whose canonical_element_id is actually in the
    # dictionary being sent to this prompt -- an alias for an element_id
    # that isn't included is useless at best. This is also what makes CV
    # extraction's category scoping (CV_EXTRACTION_CATEGORIES) actually
    # airtight: CV_ELEMENT_ID_RULE treats mapping memory as an equally valid
    # source for element_id as fit_dictionary itself, so an unfiltered
    # mapping_memory would let a CAP/TASK alias (e.g. data/mapping_memory.json's
    # illustrative "CAP-SQL" entries) leak into a CV-scoped prompt and defeat
    # the dictionary-level filtering entirely. Found via a real test
    # assertion, not assumed -- see PROJECT_NOTES.md's Phase 3 entry.
    entries = json.loads(MAPPING_MEMORY_PATH.read_text(encoding="utf-8"))
    return [entry for entry in entries if entry.get("canonical_element_id") in dictionary]


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


CV_ELEMENT_ID_RULE = """
THE RULE: element_id is copy-paste only. Before writing any element_id in
extracted_elements, find that exact string, character-for-character, already present in
the fit_dictionary JSON above (or approved_mapping_memory). If you cannot find it
verbatim, you may not use it -- not a shortened version, not an abbreviation, not a
"this is obviously what it should be called" guess. This applies even to extremely
common, unambiguous skills: SQL, Python, Excel, Git, and every other well-known tool
name are ALL subject to this rule with no exception. A skill being real, well-known, or
obviously CAP/TASK-shaped is irrelevant to whether you may write an element_id for it --
only literal presence in the dictionary you were given matters.

This dictionary NEVER includes CAP (skills) or TASK (work experience) elements, by
deliberate design -- not a temporary gap. CV extraction is scoped to Basic Info +
Education + Practical fit only; skills and work experience are always manual
candidate entry (each backed by its own AI mapping to an ESCO code, a separate,
purpose-built path -- see api/mapping_service.py), never CV-extracted. That means, for
essentially every CV you will ever process, EVERY skill/tool/task term belongs in
unmapped_terms, and extracted_elements will often end up containing only Practical fit
and education-adjacent items. That is the CORRECT, expected result -- it is not a sign
you failed to find matches, and it is not a reason to start constructing plausible-looking
IDs to fill extracted_elements.

Mechanical check before you finalize your answer: for every element_id you are about to
write in extracted_elements, re-scan the fit_dictionary JSON text above character by
character for that exact string. If this exact re-scan does not find it, delete that
extracted_elements entry and move the term to unmapped_terms instead.

Worked example: the CV says "Wrote SQL queries daily against a Postgres warehouse."
fit_dictionary contains no SQL or Postgres entry (correct -- it never contains any CAP
elements at all). Correct output:
  extracted_elements: (nothing added for SQL or Postgres)
  unmapped_terms: ["SQL", "Postgres"]
Writing element_id "CAP-SQL" here would be WRONG even though it looks like a perfectly
sensible ID -- it does not appear in fit_dictionary, so it is not available to use.
"""


CV_BASIC_INFO_RULE = """
BASIC INFO -- a separate top-level "basic_info" field, not a fit_dictionary element.
Extract phone and linkedin_url only if the CV explicitly states them (e.g. in a header
or contact section) -- set the field to null if absent, never guess or construct one
from a name. Do NOT extract or infer contact_preference under any circumstances: a CV
essentially never states how someone wants to be contacted, and this field is manual
candidate entry only (defaults to "email" until they set it themselves). If both phone
and linkedin_url are absent, set "basic_info" to null entirely rather than an object of
two nulls.
"""


CV_VALUE_SCHEMA_RULE = """
THE "value" OBJECT'S KEYS ARE NOT YOURS TO CHOOSE -- every element in fit_dictionary above
now carries its own "value_schema", showing the exact key names extracted_elements[].value.value
must use for that element_id. Copy those key names verbatim. Do not invent a different key,
rename one, abbreviate one, shorten a nested structure, or restructure it to read more
naturally -- even when your version seems clearer or more informative than the schema.

Mechanical check before you finalize your answer: for every extracted element, find that
element_id's "value_schema" in fit_dictionary above and compare it key-by-key against the
"value" object you wrote. Every key in value_schema must appear in your value object (unless
the schema marks that key nullable and you have no evidence for it); no other keys may appear.
If value_schema nests an object or array (e.g. a "languages" map, or a "values" list), your
value must use that exact same nesting -- not a flattened or renamed version of it.

Worked example: fit_dictionary shows element_id "PRACT-SPONSOR" with
value_schema {"requirement": "required|not_required|not_sure"}. The CV says "I do not require
visa sponsorship." Correct value: {"requirement": "not_required"}.
This is WRONG: {"sponsorship_required": false} -- "sponsorship_required" does not appear in
value_schema. Using it means the review screen and the comparator this element feeds will not
recognize the answer at all, silently discarding a real, correctly-extracted fact.

Another worked example: element_id "PRACT-COUNTRY" has value_schema {"current_country":
"ISO country", "presence_relative_to_vacancy": "in_country|outside_country|unknown"}. The CV
says the candidate lives in the Netherlands. Correct value: {"current_country": "Netherlands",
"presence_relative_to_vacancy": "in_country"}.
This is WRONG: {"country": "Netherlands"} -- wrong key name, and the second required key is
missing entirely.

Another worked example: element_id "PRACT-LANG" has value_schema {"languages": {"language":
"basic|working|professional|fluent|native_or_equivalent"}} -- a map from language name to
level, not a list. Correct value: {"languages": {"English": "fluent", "Dutch": "working"}}.
This is WRONG: {"languages": [{"language": "English", "level": "fluent"}]} -- a list of
objects is a different shape than the map value_schema specifies, even though it carries the
same information.
"""


def build_cv_extraction_prompt(*, candidate_id: str, cv_text: str, dictionary: Dict[str, FitElement]) -> Tuple[str, str]:
    # Hard code-level scoping (CV_EXTRACTION_CATEGORIES), not just a prompt
    # instruction -- dictionary may contain any category (it's whatever the
    # caller's load_dictionary() returned), but only PRACT/EDU ever reach the
    # model. See CV_EXTRACTION_CATEGORIES's own comment for why.
    scoped_dictionary = _scope_to_cv_extraction_categories(dictionary)
    user = _fill(
        _load_prompt("P01_cv_extraction.txt"),
        CV_TEXT=cv_text, CANDIDATE_ID=candidate_id,
        FIT_DICTIONARY_JSON=json.dumps(_dictionary_summary(scoped_dictionary, schema_field="candidate_value_schema")),
        MAPPING_MEMORY_JSON=json.dumps(_mapping_memory(scoped_dictionary)),
    )
    user += (
        f'\n\nWhen building each extracted element, set value.talent_id to "{candidate_id}" '
        f'exactly and value.source_type to "ai_extraction" exactly.'
        f'\n{CV_ELEMENT_ID_RULE}\n{CV_VALUE_SCHEMA_RULE}\n{CV_BASIC_INFO_RULE}\n{TOOL_OUTPUT_INSTRUCTIONS}'
    )
    return "You are the SHEXON CV extraction assistant described below.", user


VACANCY_STATUS_RULE = """
STOP AND READ BEFORE BUILDING extracted_elements -- two fields are easy to get wrong:

1. requirement_type is NOT the same vocabulary as this prompt's own
   "requirement_status" concept (stated_required/stated_preferred/claim/not_specified).
   requirement_type accepts ONLY these five exact values: critical, important,
   trainable, preferred, information_only. Map as follows:
     stated_required  -> critical (if the text treats it as a hard blocker) or
                         important (if required but not described as a dealbreaker)
     stated_preferred -> preferred
     claim (vague marketing language with no concrete evidence, e.g. "dynamic team",
                        "hands-on") -> do not extract this as an answered element at
                        all; instead add a note to review_flags and skip it
     not_specified    -> this means the element should not be ANSWERED in the first
                        place (see rule 2 below), so requirement_type does not apply

2. value_status/unknown_reason/not_scored_reason must follow exactly one of these
   three combinations -- do not mix them:
     answered:    value_status="answered", unknown_reason=null, not_scored_reason=null,
                  and value must be a non-empty object.
     unknown:     value_status="unknown", unknown_reason="vacancy_not_specified",
                  not_scored_reason=null. Use this whenever the vacancy text is simply
                  silent on an active element's topic -- this is the common case for
                  most elements in a short description.
     not_scored:  value_status="not_scored", not_scored_reason set, unknown_reason=null.
                  Use this ONLY when an element is deliberately out of scope for this
                  comparison (e.g. a CAP/TASK element that was never activated for this
                  vacancy) -- NOT for "the text didn't mention it", which is the
                  unknown case above.

Worked example: the vacancy text never mentions feedback frequency (ENV-FEEDBACK, an
always-active element). Correct output for that element:
  {"element_id": "ENV-FEEDBACK", "value": {"vacancy_id": ..., "element_id": "ENV-FEEDBACK",
   "value": {}, "value_status": "unknown", "unknown_reason": "vacancy_not_specified",
   "not_scored_reason": null, "source_type": "ai_extraction"}, ...}
This is WRONG: setting not_scored_reason="not_activated_for_vacancy" here -- that reason
is for elements never activated by policy, not for silence on an active one.

3. Do not return an empty or near-empty extracted_elements list as a way to avoid the
   risk of getting rule 1 or 2 wrong. An empty result is only correct if vacancy_text
   itself contains no substantive job information at all. For a real job posting, you
   must produce one entry in extracted_elements for every ALWAYS-active element in
   fit_dictionary (every PRACT/CAREER/MOT/ENV element, plus TEAM-COLLAB-INTENSITY) --
   using value_status="unknown" per rule 2 wherever the text is silent, never by
   omitting the element from extracted_elements altogether. Vacancy-activated TEAM
   elements (the other TEAM-* entries) are the only ones you should treat as not_scored
   by default, since they require an explicit hiring-manager activation this text alone
   cannot provide.
"""


VACANCY_VALUE_SCHEMA_RULE = """
THE "value" OBJECT'S KEYS ARE NOT YOURS TO CHOOSE -- every element in fit_dictionary above
now carries its own "value_schema", showing the exact key names extracted_elements[].value.value
must use for that element_id. Copy those key names verbatim. Do not invent a different key,
rename one, abbreviate one, shorten a nested structure, or restructure it to read more
naturally -- even when your version seems clearer or more informative than the schema.

Mechanical check before you finalize your answer: for every extracted element, find that
element_id's "value_schema" in fit_dictionary above and compare it key-by-key against the
"value" object you wrote. Every key in value_schema must appear in your value object (unless
the schema marks that key nullable and you have no evidence for it); no other keys may appear.
If value_schema nests an object or array, your value must use that exact same nesting -- not a
flattened or renamed version of it.

Worked example: fit_dictionary shows element_id "PRACT-SPONSOR" with
value_schema {"policy": "available|conditional|unavailable|not_specified", "conditions":
"string|null"}. The text says sponsorship is not offered to non-EU candidates. Correct value:
{"policy": "unavailable", "conditions": "Not offered for non-EU candidates"}.
This is WRONG: {"sponsorship_offered": false} -- "sponsorship_offered" does not appear in
value_schema, and "policy" is missing. Using it means the review screen and the comparator this
element feeds will not recognize the answer at all, silently discarding a real fact.

Another worked example: element_id "PRACT-COUNTRY" has value_schema {"employment_country":
"ISO country", "condition": "required|preferred|open|not_specified"}. The posting is based in
the Netherlands with an on-site/hybrid component. Correct value: {"employment_country":
"Netherlands", "condition": "required"}.
This is WRONG: {"country": "Netherlands"} -- wrong key name, and "condition" is missing
entirely.

Another worked example: element_id "PRACT-CONTRACT" has value_schema {"description":
"{\\"offered\\":[...]|\\"not_specified\\"}"} -- a nested "offered" list inside "description",
not a bare type string. Correct value: {"description": {"offered": ["full_time"]}}.
This is WRONG: {"type": "full-time"} -- wrong key name and wrong (unnested, singular) shape.
"""


def build_vacancy_extraction_prompt(*, vacancy_id: str, vacancy_text: str, dictionary: Dict[str, FitElement]) -> Tuple[str, str]:
    # Hard code-level scoping (VACANCY_EXTRACTION_EXCLUDED_CATEGORIES), not
    # just a prompt instruction -- same reasoning and same shape as
    # build_cv_extraction_prompt's own scoping above.
    scoped_dictionary = _scope_to_vacancy_extraction_categories(dictionary)
    user = _fill(
        _load_prompt("P04_vacancy_extraction.txt"),
        VACANCY_ID=vacancy_id, VACANCY_TEXT=vacancy_text,
        FIT_DICTIONARY_JSON=json.dumps(_dictionary_summary(scoped_dictionary, schema_field="vacancy_value_schema")),
        MAPPING_MEMORY_JSON=json.dumps(_mapping_memory(scoped_dictionary)),
    )
    user += (
        f'\n\nWhen building each extracted element, set value.vacancy_id to "{vacancy_id}" exactly and '
        f'value.source_type to "ai_extraction" exactly. Each extracted element also has its own '
        f'source_url and source_snapshot_id fields (siblings of value, not inside it) — a manually '
        f'pasted description has no real URL or snapshot, so set source_url to '
        f'"shexon://vacancy-description-extraction" exactly and source_snapshot_id to '
        f'"shexon-manual-extraction" exactly.'
        f'\n{VACANCY_STATUS_RULE}\n{VACANCY_VALUE_SCHEMA_RULE}\n{TOOL_OUTPUT_INSTRUCTIONS}'
    )
    return "You are the SHEXON vacancy extraction assistant described below.", user


# Embedding each element's full value_schema in the dictionary summary (so extraction
# uses canonical keys -- see CV_VALUE_SCHEMA_RULE/VACANCY_VALUE_SCHEMA_RULE above) made
# real responses longer: matching a richer schema per element means more output tokens
# per element, across up to all 41 elements for a vacancy. The prior 8192 default was
# confirmed (via real, non-mocked calls) to truncate consistently at exactly 8192 output
# tokens -- sometimes still producing a complete-looking but empty extracted_elements
# list, which passed validation silently. 16000 was confirmed sufficient (real output
# landed around 8500-9000 tokens, comfortably under the cap) across repeated real
# trials with no truncation. Note: going much higher (e.g. 24000) makes the Anthropic
# SDK require streaming for this non-streaming call ("Streaming is required for
# operations that may take longer than 10 minutes") -- 16000 stays under that threshold.
EXTRACTION_MAX_TOKENS = 16000


def run_cv_extraction(*, candidate_id: str, cv_text: str, dictionary: Dict[str, FitElement]) -> CandidateExtractionResult:
    system, user = build_cv_extraction_prompt(candidate_id=candidate_id, cv_text=cv_text, dictionary=dictionary)
    return ai_client.call_claude_structured(
        model=ai_client.MODEL_FOR_TASK["cv_extraction"], system=system, user=user,
        response_model=CandidateExtractionResult, max_tokens=EXTRACTION_MAX_TOKENS,
        task="cv_extraction", candidate_id=candidate_id,
    )


def run_vacancy_extraction(*, vacancy_id: str, vacancy_text: str, dictionary: Dict[str, FitElement]) -> VacancyExtractionResult:
    system, user = build_vacancy_extraction_prompt(vacancy_id=vacancy_id, vacancy_text=vacancy_text, dictionary=dictionary)
    return ai_client.call_claude_structured(
        model=ai_client.MODEL_FOR_TASK["vacancy_extraction"], system=system, user=user,
        response_model=VacancyExtractionResult, max_tokens=EXTRACTION_MAX_TOKENS,
        task="vacancy_extraction", vacancy_id=vacancy_id,
    )
