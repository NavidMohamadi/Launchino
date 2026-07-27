-- SHEXON v2.1.0 -> v2.1.1
-- Security/GDPR technical building blocks: explicit consent record at
-- registration. Data export/deletion are new endpoints against existing
-- columns -- no schema change needed for those.

alter table talent
    add column if not exists consent_at timestamptz,
    add column if not exists consent_version text;

alter table company
    add column if not exists consent_at timestamptz,
    add column if not exists consent_version text;
