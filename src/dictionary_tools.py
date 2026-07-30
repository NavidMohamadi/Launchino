from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from schemas import Category, FitElement


REQUIRED_MOTIVATION_IDS = {
    "MOT-LEARN", "MOT-OWNERSHIP", "MOT-STABILITY", "MOT-PROGRESSION",
    "MOT-IMPACT", "MOT-TECH-DEPTH", "MOT-VARIETY", "MOT-AUTONOMY",
    "MOT-RECOGNITION", "MOT-FINANCIAL", "MOT-LEADERSHIP", "MOT-COLLABORATION",
}


def load_fit_dictionary(path: str | Path) -> List[FitElement]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [FitElement.model_validate(item) for item in raw]


def validate_dictionary(elements: Iterable[FitElement]) -> list[str]:
    elements = list(elements)
    errors: list[str] = []
    ids = [e.element_id for e in elements]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate element_id values found")
    labels = [(e.category.value, e.label.casefold().strip()) for e in elements]
    if len(labels) != len(set(labels)):
        errors.append("Duplicate labels found within a category")
    literal_templates = {"CAP-DYNAMIC", "TASK-DYNAMIC"} & set(ids)
    if literal_templates:
        errors.append(f"Dynamic templates must not be literal canonical elements: {sorted(literal_templates)}")
    motivation_ids = {e.element_id for e in elements if e.category == Category.MOT}
    missing_mot = REQUIRED_MOTIVATION_IDS - motivation_ids
    if missing_mot:
        errors.append(f"Missing motivation elements: {sorted(missing_mot)}")
    # Per-category activation-policy correctness (CAP/TASK/MOT/TEAM) is NOT
    # re-checked here -- it was a second, independent copy of the exact same
    # rule FitElement.validate_id_and_policy (schemas.py, via
    # expected_activation_policy) already enforces at construction time, and
    # since `elements` here always comes from load_fit_dictionary()'s own
    # FitElement.model_validate() calls, a violation could never actually
    # reach this function to be reported -- dead code masquerading as a
    # real check. Removed rather than kept in sync by hand a second time
    # (found while fixing Phase 1's CAP/TASK activation-policy change, which
    # had silently drifted between this file and schemas.py already).
    return errors


def assert_valid_dictionary(path: str | Path) -> List[FitElement]:
    elements = load_fit_dictionary(path)
    errors = validate_dictionary(elements)
    if errors:
        raise ValueError("; ".join(errors))
    return elements
