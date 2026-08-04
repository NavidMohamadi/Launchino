from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from match_engine import alignment_bucket_for_percent
from schemas import Alignment, OrdinalRange


@dataclass(frozen=True)
class OrdinalComparison:
    alignment: Alignment
    reason: str
    clarification_required: bool = False
    distance_from_tolerance: int | None = None


def score_ordinal_range(
    candidate_range: OrdinalRange | None,
    vacancy_actual: int | None,
) -> OrdinalComparison:
    """Compare one role value with a candidate's explicit preferred/tolerable 1–5 ranges.

    Ordinal distance outside tolerance informs the clarification wording only; it never
    overrides the candidate's stated tolerable boundary or awards extra score.
    """
    if candidate_range is None:
        return OrdinalComparison(
            Alignment.UNKNOWN,
            "Candidate preferred and tolerable ranges have not been collected.",
            clarification_required=True,
        )
    if vacancy_actual is None:
        return OrdinalComparison(
            Alignment.UNKNOWN,
            "The vacancy does not specify the actual condition on the shared 1–5 scale.",
            clarification_required=True,
        )
    if not 1 <= vacancy_actual <= 5:
        raise ValueError("vacancy_actual must be between 1 and 5")
    if candidate_range.preferred_min <= vacancy_actual <= candidate_range.preferred_max:
        return OrdinalComparison(
            Alignment.ALIGNED,
            "The vacancy value is within the candidate's preferred range.",
        )
    if candidate_range.tolerable_min <= vacancy_actual <= candidate_range.tolerable_max:
        return OrdinalComparison(
            Alignment.POTENTIALLY_ALIGNED,
            "The vacancy value is outside the preferred range but within the stated tolerable range.",
        )
    distance = (
        candidate_range.tolerable_min - vacancy_actual
        if vacancy_actual < candidate_range.tolerable_min
        else vacancy_actual - candidate_range.tolerable_max
    )
    return OrdinalComparison(
        Alignment.MISALIGNED,
        f"The vacancy value is outside the candidate's stated tolerable range by {distance} scale point(s); confirm directly with the candidate.",
        clarification_required=True,
        distance_from_tolerance=distance,
    )


def score_ordinal_distance(
    candidate_level: Optional[int], vacancy_level: Optional[int],
) -> Tuple[Alignment, str, Optional[float]]:
    """Family 2 -- Preference/Culture-fit (v3 redesign, see PROJECT_NOTES.md):
    a single candidate 1-5 preference against a single vacancy 1-5 actual
    value, symmetric in both directions (unlike Family 1, over- and
    under-shooting are equally penalized -- there is no "requirement" here,
    just a distance). score = 100 - 20*|candidate-vacancy|, floored at 20%
    (never 0% -- even a maximally distant preference match is still a
    role, not a disqualification).

    Used by every ENV element and TEAM-COLLAB-INTENSITY (Phase 3 migrated the
    9 pre-existing ENV elements + TEAM-COLLAB-INTENSITY off
    score_ordinal_range's 4-value preferred/tolerable format onto this
    single-value shape, alongside the 4 ENV/RIASEC elements already born
    into it in Phase 1/2 -- see PROJECT_NOTES.md).
    """
    if not isinstance(candidate_level, int) or not isinstance(vacancy_level, int):
        # vacancy_level is "not_specified" (a real, documented value -- not a
        # bug path) whenever a vacancy hasn't stated an actual level yet.
        return Alignment.UNKNOWN, "Candidate or vacancy preference level is not specified.", None
    distance = abs(candidate_level - vacancy_level)
    percent = max(20.0, 100.0 - 20.0 * distance)
    reason = f"Candidate and vacancy are {distance} scale point(s) apart ({percent:.0f}% preference match)."
    return alignment_bucket_for_percent(percent), reason, percent
