from schemas import Category
from company_intake import canonicalise_company_submission
from canonical_vacancy import canonicalise_raw_vacancy
from source_schemas import (
    AcquisitionMethod, RawVacancyRecord, SourceTrustLevel, VacancyIntakeSource,
    VerificationStatus, WeightingMode,
)

WEIGHTS = {
    Category.PRACT: 15,
    Category.CAP: 30,
    Category.TASK: 25,
    Category.TEAM: 10,
    Category.CAREER: 5,
    Category.MOT: 5,
    Category.ENV: 10,
}


def test_company_and_public_use_same_canonical_profile_type():
    public = canonicalise_raw_vacancy(RawVacancyRecord(
        source_id="company_page_jsonld",
        source_record_id="page-1",
        intake_source=VacancyIntakeSource.PUBLIC_COMPANY_PAGE,
        acquisition_method=AcquisitionMethod.JSON_LD,
        source_url="https://example.com/jobs/1",
        external_job_id="1",
        company_name="Example B.V.",
        company_domain="example.com",
        title="Analyst",
        description_text="Analyse data.",
        raw_payload={"id": 1},
        trust_level=SourceTrustLevel.OFFICIAL_COMPANY_PAGE,
    ))
    direct = canonicalise_company_submission({
        "company_name": "Example B.V.",
        "company_domain": "example.com",
        "title": "Analyst",
        "description_text": "Analyse data.",
        "location_text": "Eindhoven",
    }, company_id="c1", category_weights=WEIGHTS)
    assert public.__class__ is direct.__class__
    assert public.__class__.model_fields.keys() == direct.__class__.model_fields.keys()
    assert public.weighting_mode == WeightingMode.BALANCED_DEFAULT
    assert direct.weighting_mode == WeightingMode.COMPANY_CONFIRMED
    assert direct.verification_status == VerificationStatus.COMPANY_VALIDATED


def test_public_profile_is_not_company_confirmed():
    public = canonicalise_raw_vacancy(RawVacancyRecord(
        source_id="greenhouse_public_api", source_record_id="b", intake_source="public_ats_api",
        acquisition_method="api", source_url="https://example.com", external_job_id="2",
        company_name="Example", title="Role", description_text="Description", raw_payload={"id": 2},
        trust_level=4,
    ))
    assert public.weights_confirmed_by_company is False
    assert public.verification_status == VerificationStatus.SOURCE_VERIFIED
