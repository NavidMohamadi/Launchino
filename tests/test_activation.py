import json
from pathlib import Path

from activation import is_activated, resolve_scope
from dictionary_tools import load_fit_dictionary
from schemas import NotScoredReason, UnknownReason, ValueStatus

ROOT=Path(__file__).resolve().parents[1]
D={e.element_id:e for e in load_fit_dictionary(ROOT/'data/fit_dictionary_starter.json')}


def test_always_element_is_active_and_silence_is_unknown():
    r=resolve_scope(D['PRACT-SPONSOR'],vacancy_answered=False,unknown_reason=UnknownReason.VACANCY_NOT_SPECIFIED)
    assert r.active and r.value_status==ValueStatus.UNKNOWN
    assert r.unknown_reason==UnknownReason.VACANCY_NOT_SPECIFIED


def test_candidate_selected_motivation_activation():
    assert is_activated(D['MOT-LEARN'],candidate_selected=True)
    r=resolve_scope(D['MOT-RECOGNITION'],candidate_selected=False)
    assert r.value_status==ValueStatus.NOT_SCORED
    assert r.not_scored_reason==NotScoredReason.NOT_TOP_FIVE


def test_vacancy_activated_cap_and_team_behaviour():
    assert is_activated(D['TEAM-CONFLICT'],vacancy_activated=True)
    assert not is_activated(D['TEAM-CONFLICT'],vacancy_activated=False)
    assert is_activated(D['TEAM-COLLAB-INTENSITY'])
