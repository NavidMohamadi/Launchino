from __future__ import annotations

from dataclasses import dataclass

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
