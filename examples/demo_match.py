from __future__ import annotations

import json
from pathlib import Path

from activation import resolve_scope
from dictionary_tools import load_fit_dictionary
from match_engine import aggregate_match, make_item_result, make_not_scored_item_result
from ordinal_comparators import score_ordinal_range
from schemas import (
    Alignment, Category, MatchConfiguration, NotScoredReason, OrdinalRange,
    RequirementType, UnknownReason,
)

ROOT = Path(__file__).resolve().parents[1]
dictionary = {e.element_id: e for e in load_fit_dictionary(ROOT/'data/fit_dictionary_starter.json')}
config = MatchConfiguration(
    vacancy_id='VAC-DEMO',
    category_weights={
        Category.PRACT:10, Category.CAP:30, Category.TASK:20, Category.TEAM:15,
        Category.CAREER:5, Category.MOT:10, Category.ENV:10,
    },
)
items=[]
# An always-active practical field left silent by the vacancy remains UNKNOWN.
items.append(make_item_result(
    talent_id='TALENT-A', vacancy_id='VAC-DEMO', element_id='PRACT-SPONSOR', category=Category.PRACT,
    alignment=Alignment.UNKNOWN, item_importance=5, requirement_type=RequirementType.IMPORTANT,
    reason='Vacancy sponsorship policy is not specified.', unknown_reason=UnknownReason.VACANCY_NOT_SPECIFIED,
))
# A motivation factor outside this candidate's top five is not scored.
items.append(make_not_scored_item_result(
    talent_id='TALENT-A', vacancy_id='VAC-DEMO', element_id='MOT-RECOGNITION', category=Category.MOT,
    not_scored_reason=NotScoredReason.NOT_TOP_FIVE,
))
# A selected motivation factor uses the five-point range comparator.
cmp=score_ordinal_range(OrdinalRange(preferred_min=4,preferred_max=5,tolerable_min=3,tolerable_max=5),4)
items.append(make_item_result(
    talent_id='TALENT-A', vacancy_id='VAC-DEMO', element_id='MOT-LEARN', category=Category.MOT,
    alignment=cmp.alignment, item_importance=5, requirement_type=RequirementType.IMPORTANT,
    reason=cmp.reason, clarification_required=cmp.clarification_required,
))
# A teamwork behaviour not selected by this vacancy is deliberately outside scope.
items.append(make_not_scored_item_result(
    talent_id='TALENT-A', vacancy_id='VAC-DEMO', element_id='TEAM-CONFLICT', category=Category.TEAM,
    not_scored_reason=NotScoredReason.NOT_ACTIVATED_FOR_VACANCY,
))
result=aggregate_match(talent_id='TALENT-A',vacancy_id='VAC-DEMO',item_results=items,config=config)
print(json.dumps(result.model_dump(mode='json'),indent=2))
