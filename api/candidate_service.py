"""Candidate-scoped logic shared across routers.

Two things live here:
  - resolve_candidate_element_activation / compute_candidate_completion: the
    per-category completion breakdown for the "Your profile" dashboard
    (Phase 1). Built on activation.is_activated (unmodified) using the exact
    same "what's active and answered for this candidate, no vacancy in
    scope" convention api/admin_reports.py's _candidate_coverage already
    established -- that function now calls resolve_candidate_element_activation
    too, so there's one real implementation of this rule, not two.
  - set_candidate_subscription: extracted from api/routers/candidates.py's
    PATCH .../subscription (the only prior caller) so the Premium-request
    approval flow (api/premium_requests.py) reuses the same write instead of
    reimplementing it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from activation import is_activated
from schemas import Category, ContactPreference, JobDiscoverySubscription, MatchConfiguration, SubscriptionSource, Talent

from api.matching_service import load_dictionary

CATEGORY_LABELS: Dict[Category, str] = {
    Category.EDU: "Education",
    Category.PRACT: "Practical fit",
    Category.TEAM: "How you work",
    Category.CAREER: "Where you're headed",
    Category.MOT: "What drives you",
    Category.ENV: "Your ideal environment",
    Category.CAP: "Capabilities",
    Category.TASK: "What you've done",
}

# The 8 real Fit Dictionary categories, in the fixed order the candidate
# dashboard's cards and "Continue: ..." CTA walk through (see
# frontend/src/pages/CandidateDashboardPage.jsx and PROJECT_NOTES.md's
# Phase 4 entry). Basic Info (phone/contact_preference) is
# deliberately NOT in this list -- it's a plain talent column, not a Fit
# Dictionary category, and is surfaced separately (see
# compute_candidate_completion's own "basic_info" field below), excluded
# from the overall completion percentage.
CANDIDATE_DASHBOARD_CATEGORY_ORDER: List[Category] = [
    Category.EDU, Category.PRACT, Category.TEAM, Category.CAREER,
    Category.MOT, Category.ENV, Category.CAP, Category.TASK,
]


def resolve_candidate_element_activation(conn: Connection, talent_id: UUID) -> Dict[str, Dict[str, Any]]:
    """element_id -> {"category": Category, "active": bool, "answered": bool}.

    No vacancy in scope, so VACANCY_ACTIVATED elements never resolve active
    (same as the coverage report before this refactor) and a MOT element
    counts as candidate-selected once it has an answered value -- matching
    the admin per-candidate coverage report's existing convention exactly,
    not build_item_results' match-time one (which additionally checks
    value["selected"] against a live vacancy_activated/candidate_selected
    exchange that doesn't exist outside a real match).
    """
    dictionary = load_dictionary(conn)
    latest_values = conn.execute(
        text(
            """
            select distinct on (element_id) element_id, value_status
            from talent_element_value
            where talent_id = :talent_id
            order by element_id, record_version desc
            """
        ),
        {"talent_id": str(talent_id)},
    ).all()
    value_status_by_element = {r.element_id: r.value_status for r in latest_values}

    selected_mot_ids = {
        element_id for element_id, status in value_status_by_element.items()
        if status == "answered" and dictionary.get(element_id) and dictionary[element_id].category == Category.MOT
    }

    activation: Dict[str, Dict[str, Any]] = {}
    for element in dictionary.values():
        active = is_activated(
            element, candidate_selected=element.element_id in selected_mot_ids, vacancy_activated=False,
        )
        activation[element.element_id] = {
            "category": element.category,
            "active": active,
            "answered": value_status_by_element.get(element.element_id) == "answered",
        }
    return activation


def get_premium_readiness_threshold_percent() -> float:
    """The real overall-coverage threshold match_engine.py's _assign_lane forces
    CLARIFICATION_REQUIRED below, regardless of score (src/match_engine.py:87 --
    `overall_coverage < config.minimum_overall_coverage * 100`). Read directly
    from MatchConfiguration's own field default (src/schemas.py) -- not a
    second hardcoded copy of the number. This is also the value the live Job
    Discovery pipeline actually uses unoverridden today
    (api/job_discovery_runner.py's make_deterministic_matcher constructs
    MatchConfiguration without passing minimum_overall_coverage at all).
    """
    return MatchConfiguration.model_fields["minimum_overall_coverage"].default * 100


def compute_candidate_completion(conn: Connection, talent_id: UUID) -> Dict[str, Any]:
    activation = resolve_candidate_element_activation(conn, talent_id)

    categories = []
    total_active = 0
    total_answered = 0
    for category in CANDIDATE_DASHBOARD_CATEGORY_ORDER:
        in_category = [v for v in activation.values() if v["category"] == category]
        active_count = sum(1 for v in in_category if v["active"])
        answered_count = sum(1 for v in in_category if v["active"] and v["answered"])
        total_active += active_count
        total_answered += answered_count

        if active_count == 0 or answered_count == 0:
            status, percent = "not_started", 0.0
        elif answered_count == active_count:
            status, percent = "complete", 100.0
        else:
            status, percent = "in_progress", round(answered_count / active_count * 100, 1)

        categories.append({
            "category": category,
            "label": CATEGORY_LABELS[category],
            "status": status,
            "percent_complete": percent,
            "active_item_count": active_count,
            "answered_item_count": answered_count,
        })

    overall_percent = round(total_answered / total_active * 100, 1) if total_active else 0.0

    # match_engine.py's real overall_coverage_percent is an item_importance-
    # weighted answered/active ratio (src/match_engine.py:114-117, 144) --
    # item_importance defaults to 3 uniformly (src/schemas.py) and there's no
    # vacancy in scope here to specify anything else, so that weighted ratio
    # collapses to exactly this plain answered/active count ratio. This is the
    # same quantity match_engine.py computes, not a second, different one --
    # revisit this equivalence if item_importance ever becomes candidate-
    # visible/configurable outside a specific vacancy.
    threshold_percent = get_premium_readiness_threshold_percent()

    # Basic Info: phone is a plain talent column (see PROJECT_NOTES.md's
    # Phase 1/4 entries), not a Fit Dictionary element -- deliberately
    # excluded from total_active/total_answered and overall_percent above,
    # surfaced here as its own field instead. contact_preference isn't
    # counted: it always has a real DB default ('email'), so it's never
    # meaningfully "incomplete".
    basic_info_row = conn.execute(
        text("select phone, dashboard_intro_seen from talent where talent_id = :talent_id"),
        {"talent_id": str(talent_id)},
    ).mappings().first()
    basic_info_complete = bool(basic_info_row and basic_info_row["phone"])

    return {
        "categories": categories,
        "overall_percent_complete": overall_percent,
        "premium_readiness_threshold_percent": threshold_percent,
        "premium_ready": overall_percent >= threshold_percent,
        "basic_info": {"label": "Account Settings", "complete": basic_info_complete},
        "dashboard_intro_seen": bool(basic_info_row and basic_info_row["dashboard_intro_seen"]),
    }


def mark_dashboard_intro_seen(conn: Connection, talent_id: UUID) -> None:
    """Idempotent -- called once by the frontend the moment the "What
    Launchino does for you" explainer auto-expands, so it never
    auto-expands again for this candidate (see PROJECT_NOTES.md)."""
    conn.execute(
        text("update talent set dashboard_intro_seen = true where talent_id = :talent_id"),
        {"talent_id": str(talent_id)},
    )


def set_candidate_subscription(
    conn: Connection,
    talent_id: UUID,
    *,
    job_discovery_subscription: JobDiscoverySubscription,
    subscription_expires_at,
    subscription_source: Optional[SubscriptionSource],
) -> Dict[str, Any]:
    """The one real write to talent.job_discovery_subscription et al. Reuses
    schemas.py's own Talent model for validation (unmodified), same as the
    original inline version of this code did. Raises pydantic.ValidationError
    on invalid input -- callers translate that to their own HTTP error shape.
    """
    Talent(
        talent_id=str(talent_id), full_name="placeholder", email="placeholder@example.com",
        job_discovery_subscription=job_discovery_subscription,
        subscription_expires_at=subscription_expires_at,
        subscription_source=subscription_source,
    )

    conn.execute(
        text(
            """
            update talent set
                job_discovery_subscription = :job_discovery_subscription,
                subscription_expires_at = :subscription_expires_at,
                subscription_source = :subscription_source,
                subscription_updated_at = now()
            where talent_id = :talent_id
            """
        ),
        {
            "talent_id": str(talent_id),
            "job_discovery_subscription": job_discovery_subscription.value,
            "subscription_expires_at": subscription_expires_at,
            "subscription_source": subscription_source.value if subscription_source else None,
        },
    )
    updated = conn.execute(
        text("select * from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).mappings().first()
    return dict(updated)


def set_candidate_basic_info(conn: Connection, talent_id: UUID, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Partial update of talent.phone/contact_preference -- Basic Info (see
    PROJECT_NOTES.md's Phase 1 entry), plain account columns, not a Fit
    Dictionary category. fields is payload.model_dump(exclude_unset=True)
    from api.models_api.BasicInfoUpdate: only keys actually present in the
    request are updated, so a candidate can set one field at a time without
    clobbering the others back to null. A no-op (empty fields) still returns
    the current row rather than erroring, so callers don't need a special case.
    """
    # Values of None are dropped, not written as SQL NULL: contact_preference
    # is NOT NULL at the DB level (migrations/006_v2_2_0_to_v2_3_0.sql), and a
    # null phone here just means "no change" for now, not "clear it" -- an
    # explicit null would otherwise either violate that constraint or
    # silently wipe a field the candidate didn't intend to touch.
    allowed = {"phone", "contact_preference"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if updates:
        if "contact_preference" in updates:
            updates["contact_preference"] = ContactPreference(updates["contact_preference"]).value

        # phone is required only when contact_preference is (or is becoming)
        # "phone" -- checked against the merged final state, not just this
        # request's own fields, since a partial update can set either field
        # alone while the other one's existing DB value stays in force.
        current = conn.execute(
            text("select phone, contact_preference from talent where talent_id = :talent_id"),
            {"talent_id": str(talent_id)},
        ).mappings().first()
        resulting_contact_preference = updates.get("contact_preference", current["contact_preference"])
        resulting_phone = updates.get("phone", current["phone"])
        if resulting_contact_preference == ContactPreference.PHONE.value and not resulting_phone:
            raise ValueError("phone is required when contact_preference is 'phone'")

        set_clause = ", ".join(f"{column} = :{column}" for column in updates)
        conn.execute(
            text(f"update talent set {set_clause} where talent_id = :talent_id"),
            {**updates, "talent_id": str(talent_id)},
        )
    updated = conn.execute(
        text("select * from talent where talent_id = :talent_id"), {"talent_id": str(talent_id)}
    ).mappings().first()
    return dict(updated)
