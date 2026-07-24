from datetime import date
from pathlib import Path

from ind_sponsor_registry import SponsorRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_registry_exact_kvk_match_is_company_signal():
    registry = SponsorRegistry.from_csv(ROOT / "data/fixtures/ind_recognised_sponsors_sample.csv", snapshot_date=date(2026, 7, 1))
    signal = registry.lookup("Different spelling", kvk_number="12345678")
    assert signal.recognised_sponsor is True
    assert "does not prove" in signal.note


def test_registry_non_match_does_not_claim_sponsorship():
    registry = SponsorRegistry.from_csv(ROOT / "data/fixtures/ind_recognised_sponsors_sample.csv")
    signal = registry.lookup("Completely Unrelated Company")
    assert signal.recognised_sponsor in {False, None}


def test_registry_exact_legal_name_is_verified_company_signal():
    from source_schemas import SponsorMatchMethod

    registry = SponsorRegistry.from_csv(ROOT / "data/fixtures/ind_recognised_sponsors_sample.csv")
    signal = registry.lookup("Example Analytics B.V.")
    assert signal.recognised_sponsor is True
    assert signal.match_method == SponsorMatchMethod.EXACT_LEGAL_NAME
    assert signal.human_review_required is False


def test_registry_fuzzy_name_is_only_a_possible_match():
    from source_schemas import SponsorMatchMethod

    registry = SponsorRegistry.from_csv(ROOT / "data/fixtures/ind_recognised_sponsors_sample.csv")
    signal = registry.lookup("Example Analytics BV Netherlands", fuzzy_threshold=0.75)
    assert signal.recognised_sponsor is None
    assert signal.possible_match is True
    assert signal.human_review_required is True
    assert signal.match_method == SponsorMatchMethod.FUZZY_NAME
    assert "legal entity is not yet verified" in signal.note
