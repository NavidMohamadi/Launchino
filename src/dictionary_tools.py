from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from schemas import ActivationPolicy, Category, FitElement


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
    for e in elements:
        if e.category in {Category.CAP, Category.TASK} and e.activation_policy != ActivationPolicy.VACANCY_ACTIVATED:
            errors.append(f"{e.element_id}: CAP/TASK must be vacancy_activated")
        if e.category == Category.MOT and e.activation_policy != ActivationPolicy.CANDIDATE_SELECTED:
            errors.append(f"{e.element_id}: MOT must be candidate_selected")
        if e.category == Category.TEAM and e.element_id != "TEAM-COLLAB-INTENSITY" and e.activation_policy != ActivationPolicy.VACANCY_ACTIVATED:
            errors.append(f"{e.element_id}: teamwork behaviour must be vacancy_activated")
    return errors


def assert_valid_dictionary(path: str | Path) -> List[FitElement]:
    elements = load_fit_dictionary(path)
    errors = validate_dictionary(elements)
    if errors:
        raise ValueError("; ".join(errors))
    return elements
