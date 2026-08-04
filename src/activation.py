from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from schemas import (
    ActivationPolicy, FitElement, NotScoredReason, UnknownReason, ValueStatus,
)


@dataclass(frozen=True)
class ActivationResolution:
    active: bool
    value_status: ValueStatus
    unknown_reason: UnknownReason | None = None
    not_scored_reason: NotScoredReason | None = None
    explanation: str = ""


def is_activated(
    element: FitElement,
    *,
    candidate_selected: bool = False,
    vacancy_activated: bool = False,
) -> bool:
    if element.activation_policy == ActivationPolicy.ALWAYS:
        return True
    if element.activation_policy == ActivationPolicy.CANDIDATE_SELECTED:
        return candidate_selected
    if element.activation_policy == ActivationPolicy.VACANCY_ACTIVATED:
        return vacancy_activated
    raise ValueError(f"Unsupported activation policy: {element.activation_policy}")


def resolve_scope(
    element: FitElement,
    *,
    candidate_selected: bool = False,
    vacancy_activated: bool = False,
    candidate_answered: bool = True,
    vacancy_answered: bool = True,
    unknown_reason: UnknownReason = UnknownReason.REQUIRES_VERIFICATION,
    not_scored_reason: NotScoredReason | None = None,
) -> ActivationResolution:
    active = is_activated(
        element,
        candidate_selected=candidate_selected,
        vacancy_activated=vacancy_activated,
    )
    if not active:
        if not_scored_reason is None:
            if element.activation_policy == ActivationPolicy.CANDIDATE_SELECTED:
                not_scored_reason = NotScoredReason.NOT_TOP_FIVE
            elif element.activation_policy == ActivationPolicy.VACANCY_ACTIVATED:
                not_scored_reason = NotScoredReason.NOT_ACTIVATED_FOR_VACANCY
            else:
                not_scored_reason = NotScoredReason.OUT_OF_SCOPE_BY_DESIGN
        return ActivationResolution(
            active=False,
            value_status=ValueStatus.NOT_SCORED,
            not_scored_reason=not_scored_reason,
            explanation="The element was deliberately not activated for this comparison.",
        )
    if not candidate_answered or not vacancy_answered:
        return ActivationResolution(
            active=True,
            value_status=ValueStatus.UNKNOWN,
            unknown_reason=unknown_reason,
            explanation="The element is active but one or both required values are missing or unresolved.",
        )
    return ActivationResolution(
        active=True,
        value_status=ValueStatus.ANSWERED,
        explanation="The element is active and both sides contain an answer suitable for comparison.",
    )


def _side_resolvable_policy(side: str) -> ActivationPolicy:
    return ActivationPolicy.CANDIDATE_SELECTED if side == "candidate" else ActivationPolicy.VACANCY_ACTIVATED


def _side_not_scored_reason(side: str) -> NotScoredReason:
    return NotScoredReason.NOT_TOP_FIVE if side == "candidate" else NotScoredReason.NOT_ACTIVATED_FOR_VACANCY


def resolve_extracted_value_status(
    element: FitElement,
    *,
    side: str,
    value_status: ValueStatus,
    unknown_reason: Optional[UnknownReason],
    value_payload: Dict[str, Any],
    selected_or_activated: bool,
) -> Tuple[ValueStatus, Optional[UnknownReason], Optional[NotScoredReason]]:
    """AI-extraction safeguard (v3 redesign, see PROJECT_NOTES.md): the
    extraction model may only PROPOSE a value_status; this makes the final
    not_scored/unknown decision instead, closing the gap where correctness
    previously relied only on prompt wording (see extraction_service.py's
    VACANCY_STATUS_RULE / CV extraction's equivalent instructions).

    not_scored is only ever structurally valid for the ONE activation policy
    this side can actually decide for itself -- CANDIDATE_SELECTED via the
    candidate's own "selected" flag, VACANCY_ACTIVATED via the vacancy's own
    "activated" flag (the other policy is a fact only the OTHER side could
    ever assert, e.g. a vacancy extraction has no way to know whether some
    future candidate will pick a given MOT priority as a top-five, so
    not_scored/not_top_five is never a vacancy-side call to make). Every
    other case is corrected to answered/unknown purely from whether real
    data is present, regardless of what value_status the model itself
    proposed -- if its own proposal already agrees with that correction, its
    more specific unknown_reason is kept rather than replaced with a generic
    fallback; if it disagrees, the reason is generic because its own
    reasoning can no longer be trusted here.
    """
    if element.activation_policy == _side_resolvable_policy(side) and not selected_or_activated:
        return ValueStatus.NOT_SCORED, None, _side_not_scored_reason(side)

    corrected_status = ValueStatus.ANSWERED if value_payload else ValueStatus.UNKNOWN
    if corrected_status == value_status:
        return corrected_status, (unknown_reason if corrected_status == ValueStatus.UNKNOWN else None), None
    if corrected_status == ValueStatus.UNKNOWN:
        return ValueStatus.UNKNOWN, UnknownReason.REQUIRES_VERIFICATION, None
    return ValueStatus.ANSWERED, None, None
