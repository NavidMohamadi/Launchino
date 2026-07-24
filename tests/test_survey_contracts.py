import json
from pathlib import Path

from survey_contracts import assert_contracts, validate_range_contracts

ROOT=Path(__file__).resolve().parents[1]


def test_all_survey_dictionary_contracts(): assert_contracts(ROOT)


def test_all_twelve_vacancy_motivation_factors_present():
    d=json.loads((ROOT/'data/vacancy_workshop.json').read_text())
    assert len(d['motivation_matrix'])==12


def test_environment_and_motivation_use_five_point_scales():
    d=json.loads((ROOT/'data/fit_dictionary_starter.json').read_text())
    for e in d:
        if e['category'] in {'ENV','MOT'}:
            assert e['comparator_key']=='ordinal_range'
            assert 'scale_id' in e['candidate_value_schema']
            assert 'scale_id' in e['vacancy_value_schema']
