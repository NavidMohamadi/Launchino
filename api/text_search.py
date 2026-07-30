"""Shared local text-similarity pre-filter -- used both by
api/mapping_service.py's ESCO/ISCED shortlisting (Phase 2) and
api/reference_search.py's institution/programme search (Phase 4), so the
same fuzzy-matching rule isn't reimplemented twice (see PROJECT_NOTES.md's
Phase 1 entry on why that's worth avoiding). Same mechanism
src/ind_sponsor_registry.py's SponsorRegistry.lookup() already uses for
company-name matching: difflib.SequenceMatcher over normalised text, with
an exact-match-first check.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List

from vacancy_utils import normalise_text


def shortlist_by_text_similarity(
    raw_term: str, options: List[Dict[str, Any]], *, label_field: str = "label", limit: int = 20,
) -> List[Dict[str, Any]]:
    target = normalise_text(raw_term)
    if not target:
        return []
    scored = []
    for option in options:
        normalised = normalise_text(option[label_field])
        if normalised == target:
            score = 1.0
        else:
            score = SequenceMatcher(None, target, normalised).ratio()
            if target in normalised or normalised in target:
                score = max(score, 0.75)
        if score > 0:
            scored.append((score, option))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [option for _, option in scored[:limit]]
