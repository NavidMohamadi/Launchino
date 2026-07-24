from pathlib import Path

from public_weighting import derive_requirement_from_text, load_public_weight_profile
from schemas import RequirementType

ROOT = Path(__file__).resolve().parents[1]


def test_public_weights_sum_to_100():
    weights = load_public_weight_profile(ROOT / "data/public_weight_profile.json")
    assert sum(weights.values()) == 100


def test_required_text_is_critical_provisional_signal():
    importance, requirement_type, reason = derive_requirement_from_text("SQL is required for this role")
    assert importance == 5
    assert requirement_type == RequirementType.CRITICAL
    assert "public vacancy text" in reason


def test_preferred_text_is_not_critical():
    importance, requirement_type, _ = derive_requirement_from_text("Python is nice to have")
    assert importance == 2
    assert requirement_type == RequirementType.PREFERRED
