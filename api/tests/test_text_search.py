"""Pure-logic tests for api/text_search.py's shortlist_by_text_similarity --
shared between api/mapping_service.py (ESCO/ISCED shortlisting) and
api/reference_search.py (institution/programme search)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from api.text_search import shortlist_by_text_similarity  # noqa: E402

OPTIONS = [
    {"uri": "u:sql", "label": "SQL"},
    {"uri": "u:mysql", "label": "MySQL"},
    {"uri": "u:python", "label": "Python (programming language)"},
    {"uri": "u:excel", "label": "Microsoft Excel"},
]


def test_exact_match_ranks_first():
    result = shortlist_by_text_similarity("SQL", OPTIONS)
    assert result[0]["uri"] == "u:sql"


def test_partial_match_included_but_ranked_below_exact():
    result = shortlist_by_text_similarity("sql", OPTIONS)
    uris = [r["uri"] for r in result]
    assert uris[0] == "u:sql"
    assert "u:mysql" in uris


def test_empty_for_blank_term():
    assert shortlist_by_text_similarity("   ", OPTIONS) == []


def test_respects_limit():
    many = [{"uri": f"u:{i}", "label": f"Skill {i}"} for i in range(50)]
    result = shortlist_by_text_similarity("Skill", many, limit=5)
    assert len(result) == 5


def test_custom_label_field():
    options = [{"code": "1", "name": "University of Amsterdam"}, {"code": "2", "name": "Delft University"}]
    result = shortlist_by_text_similarity("Amsterdam", options, label_field="name")
    assert result[0]["code"] == "1"
