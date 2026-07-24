import json
from pathlib import Path

from source_schemas import CanonicalVacancyProfile

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_form_has_source_role_weights_quality_sections():
    data = json.loads((ROOT / "data/canonical_vacancy_form.json").read_text())
    ids = {row["section_id"] for row in data["sections"]}
    assert ids == {"source_metadata", "basic_job_data", "role_fit_profile", "weights", "quality"}
    form_fields = {field for row in data["sections"] for field in row["fields"] if not field.endswith(" elements")}
    required = {"vacancy_id", "intake_source", "verification_status", "weighting_mode", "provenance"}
    assert required <= form_fields
