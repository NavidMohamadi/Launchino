"""Fills prompts/P08 and runs it through Claude to produce a plain-text match explanation.

P08's own OUTPUT JSON block describes a structured breakdown (summary,
strongest_alignments, material_gaps, unknowns, ...), but source_schemas.py's
JobRecommendation.explanation is a single str field, and job_recommendation
(src/database_schema.sql) has one text column for it -- there is nowhere to
persist that richer structure. Rather than force it and flatten it, this
asks Claude for prose directly, covering the same ground P08 asks for.

job_discovery_pipeline.py's ExplanationGenerator signature is
(talent, match_result, vacancy) -> str -- it does not pass the underlying
ItemResult list, so this explanation is built from MatchResult's own
category-level breakdown (score/coverage/critical/unknown counts per
category, plus critical_flags/clarification_flags), not per-item reasons.
"""

from __future__ import annotations

import json
from typing import Tuple

from schemas import MatchResult, Talent
from source_schemas import CanonicalVacancyProfile

from api import REPO_ROOT, ai_client

PROMPTS_DIR = REPO_ROOT / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def build_match_explanation_prompt(*, match_result: MatchResult, vacancy: CanonicalVacancyProfile) -> Tuple[str, str]:
    template = _load_prompt("P08_match_explanation.txt")
    user = template.replace(
        "{{MATCH_RESULT_JSON}}", json.dumps(match_result.model_dump(mode="json"), default=str),
    )
    user = user.replace(
        "{{ITEM_RESULTS_JSON}}",
        "[] (not available to this generator; rely on calculated_match_result's category_results instead)",
    )
    user += (
        f"\n\nWrite your answer as plain prose (2-4 short paragraphs) for a human reviewer, not the "
        f"OUTPUT JSON shape described above -- there is nowhere structured to store that breakdown. "
        f"Cover the same ground: major alignments, material gaps, unknowns, critical issues, "
        f"bridgeability, and evidence limitations, for the role \"{vacancy.title}\" at "
        f"{vacancy.company_name}. Do not recalculate or contradict the score, coverage, or lane "
        f"already computed; only explain them. Do not include any JSON in your answer."
    )
    return "You are the SHEXON match explanation assistant described below.", user


def generate_match_explanation(*, talent: Talent, match_result: MatchResult, vacancy: CanonicalVacancyProfile) -> str:
    system, user = build_match_explanation_prompt(match_result=match_result, vacancy=vacancy)
    return ai_client.call_claude_text(
        model=ai_client.MODEL_FOR_TASK["match_explanation"], system=system, user=user,
        task="match_explanation", candidate_id=str(talent.talent_id), vacancy_id=str(vacancy.vacancy_id),
    )
