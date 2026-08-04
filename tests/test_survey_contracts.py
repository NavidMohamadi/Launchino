import json
from pathlib import Path

from survey_contracts import assert_contracts, validate_range_contracts

ROOT=Path(__file__).resolve().parents[1]


def test_all_survey_dictionary_contracts(): assert_contracts(ROOT)


def test_all_thirteen_vacancy_motivation_factors_present():
    # 12 original + MOT-CHALLENGE (v3 redesign, see PROJECT_NOTES.md).
    d=json.loads((ROOT/'data/vacancy_workshop.json').read_text())
    assert len(d['motivation_matrix'])==13


# v3 redesign, Phase 3 (see PROJECT_NOTES.md): the pre-existing ENV/MOT
# elements have now been migrated off the old 4-value ordinal_range/scale_id
# format onto the same single-value Family 2/3 schema the new elements were
# already born into during Phase 1/2 -- no more split, one uniform format
# per category. TEAM-COLLAB-INTENSITY is Family 2 too (a preference, not a
# capability, per the v3 spec), so it gets the same ordinal_distance check.


def test_environment_and_motivation_use_five_point_scales():
    d=json.loads((ROOT/'data/fit_dictionary_starter.json').read_text())
    for e in d:
        if e['category'] not in {'ENV','MOT'} and e['element_id'] != 'TEAM-COLLAB-INTENSITY':
            continue
        assert e['comparator_key'] in {'ordinal_distance', 'motivation_preferred_minimum'}
        assert 'scale_id' not in e['candidate_value_schema']
        assert 'scale_id' not in e['vacancy_value_schema']
