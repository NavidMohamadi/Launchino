import pytest
from pydantic import ValidationError

from ordinal_comparators import score_ordinal_range
from schemas import Alignment, OrdinalRange


def rng(): return OrdinalRange(preferred_min=3,preferred_max=4,tolerable_min=2,tolerable_max=5)

def test_preferred_range_is_aligned(): assert score_ordinal_range(rng(),4).alignment==Alignment.ALIGNED

def test_tolerable_not_preferred_is_potential(): assert score_ordinal_range(rng(),5).alignment==Alignment.POTENTIALLY_ALIGNED

def test_outside_tolerance_is_misaligned_and_flagged():
    r=score_ordinal_range(OrdinalRange(preferred_min=2,preferred_max=3,tolerable_min=1,tolerable_max=4),5)
    assert r.alignment==Alignment.MISALIGNED and r.clarification_required and r.distance_from_tolerance==1

def test_missing_is_unknown(): assert score_ordinal_range(None,3).alignment==Alignment.UNKNOWN

def test_range_must_be_nested():
    with pytest.raises(ValidationError): OrdinalRange(preferred_min=1,preferred_max=4,tolerable_min=2,tolerable_max=5)
