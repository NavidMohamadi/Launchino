from __future__ import annotations

from dataclasses import dataclass

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
