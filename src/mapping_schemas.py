from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MappingResponse(BaseModel):
    """Raw shape Claude fills via the forced tool call in api/mapping_service.py.

    Identical for all three mapping kinds (skill->ESCO, occupation->ESCO,
    program->ISCED-F): "pick the best match from the list you were given, or
    say none genuinely fits." matched_code/matched_label are null together
    when nothing fits -- never a code with no label or vice versa.
    """

    matched_code: Optional[str] = Field(
        default=None,
        description=(
            "Must be copied EXACTLY, character-for-character, from the chosen option's "
            "own identifier field in the list you were given (its 'uri' for a skill/"
            "occupation shortlist, or its 'code' for a fixed ISCED/NACE list) -- never "
            "typed from memory. Never substitute a code from a different classification "
            "system you happen to recognize (e.g. an ISCO occupation group code, a SOC "
            "code, a NAICS code) even if it feels more standard or precise than the "
            "option's own identifier -- doing so will cause the match to be discarded as "
            "invented, even when your judgement was correct. If nothing genuinely "
            "matches, use null here, not a code from outside the given list."
        ),
    )
    matched_label: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class MappingResult(BaseModel):
    """Public result of a skill/occupation/program mapping call.

    requires_confirmation mirrors src/ind_sponsor_registry.py's
    human_review_required flag on CompanySponsorshipSignal -- the same
    "never silently accept uncertain AI output" shape applied to a different
    kind of match. True whenever nothing matched at all, or confidence is
    below MAPPING_CONFIDENCE_THRESHOLD; the caller (the candidate, via the
    survey UI) must confirm or correct the mapping before it is treated as
    settled -- never persisted as-is just because Claude returned an answer.
    """

    matched_code: Optional[str] = None
    matched_label: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    reasoning: str
