from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from schemas import Category, FitElement, FitElementAlias, MappingRelationship, SharingStatus, expected_activation_policy


SLUG_RE = re.compile(r"[^A-Z0-9]+")


def slugify_label(label: str) -> str:
    slug = SLUG_RE.sub("-", label.upper()).strip("-")
    if not slug:
        raise ValueError("Cannot mint an element ID from an empty label")
    return slug[:60]


def mint_element_id(category: Category, label: str, existing_ids: Iterable[str]) -> str:
    base = f"{category.value}-{slugify_label(label)}"
    existing = set(existing_ids)
    if base not in existing:
        return base
    counter = 2
    while f"{base}-{counter}" in existing:
        counter += 1
    return f"{base}-{counter}"


@dataclass
class MappingMemory:
    aliases: Dict[str, str]

    @classmethod
    def from_json(cls, path: str | Path) -> "MappingMemory":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({entry["alias"].casefold().strip(): entry["canonical_element_id"] for entry in raw})

    def resolve_approved_alias(self, raw_term: str) -> Optional[str]:
        return self.aliases.get(raw_term.casefold().strip())

    def remember_approved_alias(self, alias: FitElementAlias) -> None:
        self.aliases[alias.alias.casefold().strip()] = alias.canonical_element_id


def normalisation_decision(
    raw_term: str,
    proposed_element_id: str | None,
    relationship: MappingRelationship,
    confidence: float,
    approved_memory: MappingMemory,
    minimum_ai_confidence: float = 0.90,
) -> dict:
    remembered = approved_memory.resolve_approved_alias(raw_term)
    if remembered:
        return {"decision": "approved_mapping", "element_id": remembered, "source": "mapping_memory"}
    if relationship in {MappingRelationship.EXACT, MappingRelationship.SYNONYM} and confidence >= minimum_ai_confidence and proposed_element_id:
        return {
            "decision": "human_confirmation_required",
            "element_id": proposed_element_id,
            "source": "ai_proposal",
        }
    return {"decision": "dictionary_review_required", "element_id": None, "source": "unmapped_or_weak"}



def build_approved_dynamic_element(
    *,
    category: Category,
    element_id: str,
    label: str,
    definition: str,
    candidate_question: str,
    vacancy_question: str,
    evidence_rule: str,
) -> FitElement:
    """Create a reviewed CAP/TASK element; activation is system-derived, never reviewer-selected.

    Calls expected_activation_policy() (schemas.py) rather than hardcoding a
    literal here -- this is exactly the "system-derived" the docstring
    already promised, and avoids a second copy of the same CAP/TASK rule
    silently drifting out of sync with FitElement's own validator (which
    already happened once -- see PROJECT_NOTES.md)."""
    if category not in {Category.CAP, Category.TASK}:
        raise ValueError("Dynamic elements may only be created for CAP or TASK")
    return FitElement(
        element_id=element_id,
        category=category,
        label=label,
        definition=definition,
        activation_policy=expected_activation_policy(category, element_id),
        candidate_question=candidate_question,
        vacancy_question=vacancy_question,
        candidate_value_schema={"level":"integer 0..4", "evidence":"string|null"},
        vacancy_value_schema={"required_level":"integer 0..4", "activated":"boolean"},
        evidence_rule=evidence_rule,
        comparator_key="ordinal_requirement",
        sharing_status=SharingStatus.CANDIDATE_VISIBLE,
        version="2.0.0",
    )
