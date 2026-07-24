from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dictionary_tools import load_fit_dictionary


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_range_contracts(dictionary_path: str | Path, scale_path: str | Path) -> list[str]:
    elements = load_fit_dictionary(dictionary_path)
    scales = load_json(scale_path)
    errors: list[str] = []
    for e in elements:
        if e.comparator_key != "ordinal_range":
            continue
        cscale = e.candidate_value_schema.get("scale_id")
        vscale = e.vacancy_value_schema.get("scale_id")
        if not cscale or cscale != vscale:
            errors.append(f"{e.element_id}: candidate and vacancy scale_id must match")
        elif cscale not in scales:
            errors.append(f"{e.element_id}: unknown scale_id {cscale}")
        for key in ["preferred_min","preferred_max","tolerable_min","tolerable_max"]:
            if key not in e.candidate_value_schema:
                errors.append(f"{e.element_id}: missing candidate range field {key}")
        if "actual" not in e.vacancy_value_schema:
            errors.append(f"{e.element_id}: missing vacancy actual field")
    return errors


def validate_motivation_survey_contract(candidate_survey_path: str | Path, vacancy_workshop_path: str | Path, dictionary_path: str | Path) -> list[str]:
    candidate = load_json(candidate_survey_path)
    vacancy = load_json(vacancy_workshop_path)
    elements = load_fit_dictionary(dictionary_path)
    mot_ids = {e.element_id for e in elements if e.category.value == "MOT"}
    errors: list[str] = []
    if set(candidate.get("motivation_factors", [])) != mot_ids:
        errors.append("Candidate survey motivation factor IDs do not match the dictionary")
    matrix_ids = {x["element_id"] for x in vacancy.get("motivation_matrix", [])}
    if matrix_ids != mot_ids:
        errors.append("Vacancy motivation matrix does not include all twelve dictionary factors")
    return errors


def assert_contracts(root: str | Path) -> None:
    root = Path(root)
    errors = []
    errors += validate_range_contracts(root/'data/fit_dictionary_starter.json', root/'data/scale_definitions.json')
    errors += validate_motivation_survey_contract(
        root/'data/candidate_survey.json', root/'data/vacancy_workshop.json', root/'data/fit_dictionary_starter.json'
    )
    if errors:
        raise ValueError("; ".join(errors))
