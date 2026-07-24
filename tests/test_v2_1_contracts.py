from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_matching_engine_is_subscription_unaware():
    source = (ROOT / "src/match_engine.py").read_text(encoding="utf-8").lower()
    assert "subscription" not in source
    assert "entitlement" not in source


def test_v2_1_database_fields_and_tables_exist():
    sql = (ROOT / "src/database_schema.sql").read_text(encoding="utf-8")
    for token in (
        "job_discovery_subscription",
        "subscription_expires_at",
        "job_discovery_campaign_opt_in",
        "last_material_change_at",
        "create table job_discovery_batch_run",
        "create table preliminary_opportunity_signal",
        "check (ai_explanation_generated=false)",
        "check (vacancy_details_visible=false)",
    ):
        assert token in sql


def test_v2_1_migration_is_present_and_defaults_existing_talents_to_none():
    sql = (ROOT / "migrations/003_v2_0_1_to_v2_1_0.sql").read_text(encoding="utf-8")
    assert "default 'none'" in sql
    assert "subscription_expires_at" in sql
    assert "preliminary_opportunity_signal" in sql


def test_pre_v2_prompts_remain_present_and_unchanged_in_scope():
    prompts = ROOT / "prompts"
    for number in range(1, 22):
        matches = list(prompts.glob(f"P{number:02d}_*.txt"))
        assert len(matches) == 1


def test_package_documents_the_separate_full_and_campaign_paths():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "full Job Discovery" in readme
    assert "preliminary" in readme.lower()
    assert "company-direct" in readme.lower()
