import json
from pathlib import Path

from activation import is_activated, resolve_extracted_value_status, resolve_scope
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


# -- AI-extraction safeguard (v3 redesign, see PROJECT_NOTES.md): the
# extraction model may only PROPOSE a value_status; resolve_extracted_value_status
# makes the final not_scored/unknown decision, closing the gap where
# correctness previously relied only on prompt wording. --

def test_extracted_candidate_selected_not_selected_forces_not_scored():
    # Model proposed "answered" for MOT-LEARN even though selected=False --
    # the code, not the model's own guess, must win.
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['MOT-LEARN'], side='candidate', value_status=ValueStatus.ANSWERED, unknown_reason=None,
        value_payload={'preferred_level': 4}, selected_or_activated=False,
    )
    assert status == ValueStatus.NOT_SCORED
    assert not_scored_reason == NotScoredReason.NOT_TOP_FIVE
    assert unknown_reason is None


def test_extracted_candidate_selected_true_with_data_is_answered():
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['MOT-LEARN'], side='candidate', value_status=ValueStatus.ANSWERED, unknown_reason=None,
        value_payload={'preferred_level': 4, 'minimum_acceptable_level': 2}, selected_or_activated=True,
    )
    assert status == ValueStatus.ANSWERED
    assert not_scored_reason is None and unknown_reason is None


def test_extracted_vacancy_activated_false_forces_not_scored_even_if_model_said_answered():
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['TEAM-CONFLICT'], side='vacancy', value_status=ValueStatus.ANSWERED, unknown_reason=None,
        value_payload={'required_level': 0}, selected_or_activated=False,
    )
    assert status == ValueStatus.NOT_SCORED
    assert not_scored_reason == NotScoredReason.NOT_ACTIVATED_FOR_VACANCY


def test_extracted_vacancy_activated_true_with_data_is_answered():
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['TEAM-CONFLICT'], side='vacancy', value_status=ValueStatus.ANSWERED, unknown_reason=None,
        value_payload={'required_level': 4}, selected_or_activated=True,
    )
    assert status == ValueStatus.ANSWERED


def test_extracted_always_element_not_scored_guess_is_corrected():
    # PRACT-SPONSOR is ALWAYS-active -- not_scored is structurally impossible
    # here regardless of what the model itself proposed; the safeguard
    # re-derives from whether real data is actually present.
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['PRACT-SPONSOR'], side='candidate', value_status=ValueStatus.NOT_SCORED, unknown_reason=None,
        value_payload={'requirement': 'not_required'}, selected_or_activated=False,
    )
    assert status == ValueStatus.ANSWERED
    assert not_scored_reason is None and unknown_reason is None


def test_extracted_always_element_not_scored_guess_with_no_data_becomes_unknown():
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['PRACT-SPONSOR'], side='candidate', value_status=ValueStatus.NOT_SCORED, unknown_reason=None,
        value_payload={}, selected_or_activated=False,
    )
    assert status == ValueStatus.UNKNOWN
    assert unknown_reason == UnknownReason.REQUIRES_VERIFICATION


def test_extracted_motivation_element_not_scored_never_valid_on_vacancy_side():
    # A vacancy extraction has no way to know whether any future candidate
    # will pick this MOT priority as a top-five -- not_scored/not_top_five is
    # never a vacancy-side call to make, even if the model proposed it.
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['MOT-LEARN'], side='vacancy', value_status=ValueStatus.NOT_SCORED, unknown_reason=None,
        value_payload={'actual_level': 4}, selected_or_activated=False,
    )
    assert status == ValueStatus.ANSWERED


def test_extracted_status_agreeing_with_correction_keeps_specific_unknown_reason():
    # The model's own unknown_reason (candidate_declined) is more specific
    # than the generic fallback -- kept when the top-level status agrees.
    status, unknown_reason, not_scored_reason = resolve_extracted_value_status(
        D['PRACT-SPONSOR'], side='candidate', value_status=ValueStatus.UNKNOWN,
        unknown_reason=UnknownReason.CANDIDATE_DECLINED, value_payload={}, selected_or_activated=False,
    )
    assert status == ValueStatus.UNKNOWN
    assert unknown_reason == UnknownReason.CANDIDATE_DECLINED
