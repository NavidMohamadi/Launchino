import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from dictionary_tools import assert_valid_dictionary
from normalisation_registry import build_approved_dynamic_element
from schemas import (
    ActivationPolicy, ApprovedAliasRelationship, Category, FitElement, FitElementAlias,
    FitElementProposal, NotScoredReason, SourceType, TalentElementValue, UnknownReason, ValueStatus,
)

ROOT=Path(__file__).resolve().parents[1]


def test_dictionary_policies_validate():
    els=assert_valid_dictionary(ROOT/'data/fit_dictionary_starter.json')
    assert els


def test_cap_task_proposal_only():
    FitElementProposal(raw_term='SQL',proposed_element_id='CAP-SQL',proposed_category=Category.CAP,proposed_label='SQL',proposed_definition='Query data',reason_new_element_is_needed='new',proposed_by='x')
    with pytest.raises(ValidationError):
        FitElementProposal(raw_term='new value',proposed_element_id='ENV-X',proposed_category=Category.ENV,proposed_label='X',proposed_definition='x',reason_new_element_is_needed='new',proposed_by='x')


def test_approved_alias_cannot_be_unmapped():
    with pytest.raises(ValidationError):
        FitElementAlias(alias='x',canonical_element_id='CAP-X',relationship='unmapped',approved_by='a',approved_at=date.today())


def test_dynamic_element_policy_is_derived():
    e=build_approved_dynamic_element(category=Category.CAP,element_id='CAP-POWER-BI',label='Power BI',definition='Create BI reports',candidate_question='Evidence?',vacancy_question='Required?',evidence_rule='Example')
    assert e.activation_policy==ActivationPolicy.VACANCY_ACTIVATED


def test_value_status_reason_consistency():
    with pytest.raises(ValidationError):
        TalentElementValue(talent_id='T',element_id='MOT-X',value_status=ValueStatus.NOT_SCORED,source_type=SourceType.SELF_REPORT)
    TalentElementValue(talent_id='T',element_id='MOT-X',value_status=ValueStatus.NOT_SCORED,not_scored_reason=NotScoredReason.NOT_TOP_FIVE,source_type=SourceType.SELF_REPORT)
    TalentElementValue(talent_id='T',element_id='PRACT-X',value_status=ValueStatus.UNKNOWN,unknown_reason=UnknownReason.CANDIDATE_NOT_ANSWERED,source_type=SourceType.SELF_REPORT)
