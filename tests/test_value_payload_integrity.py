from datetime import date

import pytest
from pydantic import ValidationError

from schemas import (
    NotScoredReason, SourceType, TalentElementValue, UnknownReason,
    VacancyElementValue, ValueStatus,
)


def test_answered_talent_value_rejects_empty_payload():
    with pytest.raises(ValidationError, match="non-empty value payload"):
        TalentElementValue(
            talent_id="T1", element_id="ENV-STRUCTURE", value={},
            value_status=ValueStatus.ANSWERED, source_type=SourceType.SELF_REPORT,
        )


def test_answered_vacancy_value_rejects_empty_payload():
    with pytest.raises(ValidationError, match="non-empty value payload"):
        VacancyElementValue(
            vacancy_id="V1", element_id="ENV-STRUCTURE", value={},
            value_status=ValueStatus.ANSWERED, source_type=SourceType.HIRING_MANAGER,
        )


def test_answered_values_accept_non_empty_payloads():
    talent = TalentElementValue(
        talent_id="T1", element_id="ENV-STRUCTURE", value={"preferred_min": 2},
        value_status=ValueStatus.ANSWERED, source_type=SourceType.SELF_REPORT,
    )
    vacancy = VacancyElementValue(
        vacancy_id="V1", element_id="ENV-STRUCTURE", value={"actual": 3},
        value_status=ValueStatus.ANSWERED, source_type=SourceType.HIRING_MANAGER,
    )
    assert talent.value and vacancy.value


def test_unknown_value_may_have_empty_payload():
    value = VacancyElementValue(
        vacancy_id="V1", element_id="PRACT-SPONSOR", value={},
        value_status=ValueStatus.UNKNOWN,
        unknown_reason=UnknownReason.VACANCY_NOT_SPECIFIED,
        source_type=SourceType.JOB_DESCRIPTION,
    )
    assert value.value == {}


def test_not_scored_value_may_have_empty_payload():
    value = TalentElementValue(
        talent_id="T1", element_id="MOT-RECOGNITION", value={},
        value_status=ValueStatus.NOT_SCORED,
        not_scored_reason=NotScoredReason.NOT_TOP_FIVE,
        source_type=SourceType.SELF_REPORT,
    )
    assert value.value == {}
