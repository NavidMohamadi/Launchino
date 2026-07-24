from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Dict

from schemas import Category, RequirementType
from source_schemas import WeightingMode


REQUIRED_PATTERNS = re.compile(r"\b(must|required|mandatory|essential|need to|you have)\b", re.I)
PREFERRED_PATTERNS = re.compile(r"\b(preferred|nice to have|advantage|plus|desirable)\b", re.I)
TRAINABLE_PATTERNS = re.compile(r"\b(willing to learn|training provided|can be learned|development opportunity)\b", re.I)


def derive_requirement_from_text(text: str) -> tuple[int, RequirementType, str]:
    if REQUIRED_PATTERNS.search(text):
        return 5, RequirementType.CRITICAL, "Explicit required-language signal in public vacancy text"
    if PREFERRED_PATTERNS.search(text):
        return 2, RequirementType.PREFERRED, "Explicit preferred-language signal in public vacancy text"
    if TRAINABLE_PATTERNS.search(text):
        return 3, RequirementType.TRAINABLE, "Explicit trainability signal in public vacancy text"
    return 3, RequirementType.IMPORTANT, "Neutral provisional importance because the text is not explicit"


def load_public_weight_profile(path: str | Path) -> Dict[Category, float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    weights = {Category(k): float(v) for k, v in data["category_weights"].items()}
    if abs(sum(weights.values()) - 100.0) > 0.01:
        raise ValueError("Public weight profile must sum to 100")
    return weights


def public_weighting_mode(company_confirmed: bool, explicit_text_signals: bool) -> WeightingMode:
    if company_confirmed:
        return WeightingMode.COMPANY_CONFIRMED
    return WeightingMode.TEXT_DERIVED if explicit_text_signals else WeightingMode.BALANCED_DEFAULT
