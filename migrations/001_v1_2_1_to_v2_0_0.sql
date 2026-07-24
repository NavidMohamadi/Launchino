-- Reference migration outline from v1.2.1 to v2.0.0.
-- This is intentionally conservative and must be adapted to the deployed database.

begin;

create table if not exists company (
    company_id uuid primary key default gen_random_uuid(),
    legal_name text not null,
    display_name text not null,
    website_domain text not null,
    career_page_url text,
    country_code text,
    kvk_number text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table vacancy add column if not exists company_name text;
alter table vacancy add column if not exists company_domain text;
alter table vacancy add column if not exists description_text text;
alter table vacancy add column if not exists primary_source_url text;
alter table vacancy add column if not exists apply_url text;
alter table vacancy add column if not exists external_job_ids jsonb not null default '{}'::jsonb;
alter table vacancy add column if not exists intake_sources jsonb not null default '[]'::jsonb;
alter table vacancy add column if not exists acquisition_methods jsonb not null default '[]'::jsonb;
alter table vacancy add column if not exists verification_status text not null default 'auto_extracted';
alter table vacancy add column if not exists lifecycle_status text not null default 'draft';
alter table vacancy add column if not exists weighting_mode text not null default 'balanced_default';
alter table vacancy add column if not exists weights_confirmed_by_company boolean not null default false;
alter table vacancy add column if not exists category_weights jsonb not null default '{}'::jsonb;
alter table vacancy add column if not exists canonical_key text;
alter table vacancy add column if not exists content_hash text;
alter table vacancy add column if not exists first_seen_at timestamptz not null default now();
alter table vacancy add column if not exists last_seen_at timestamptz not null default now();
alter table vacancy add column if not exists missing_poll_count integer not null default 0;
alter table vacancy add column if not exists record_version integer not null default 1;

-- Create source_policy, company_job_source, poll_run, source_snapshot,
-- vacancy_source_link, vacancy_field_provenance, vacancy_source_conflict and
-- job_recommendation using the definitions in src/database_schema.sql.
-- Backfill company_name, description_text, canonical_key and content_hash before
-- making those fields NOT NULL in a production migration.

commit;
