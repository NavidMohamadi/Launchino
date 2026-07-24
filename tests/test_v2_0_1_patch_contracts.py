from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_database_schema_uses_non_unique_canonical_lookup_and_review_queue():
    sql = (ROOT / "src/database_schema.sql").read_text(encoding="utf-8")
    assert "create index vacancy_canonical_lookup_idx" in sql
    assert "create unique index vacancy_canonical_active_idx" not in sql
    assert "create table vacancy_dedup_review" in sql


def test_database_schema_requires_approval_when_source_is_enabled():
    sql = (ROOT / "src/database_schema.sql").read_text(encoding="utf-8")
    assert "check (not enabled or terms_review_status='approved')" in sql


def test_v2_0_1_migration_contains_lifecycle_audit_fields():
    sql = (ROOT / "migrations/002_v2_0_0_to_v2_0_1.sql").read_text(encoding="utf-8")
    for field in ("closed_reason", "closed_at", "reopened_at", "reopened_reason"):
        assert field in sql
