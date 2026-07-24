-- SHEXON Talent Fit + Job Discovery v2.0.0 -> v2.0.1
-- Maintenance patch: fail-closed source policy, reversible vacancy closure,
-- indexed dedup candidate generation and explicit duplicate-review queue.

begin;

alter table source_policy
    add constraint source_policy_enabled_requires_approval
    check (not enabled or terms_review_status='approved') not valid;

-- Validate after existing rows have been reviewed and corrected.
alter table source_policy validate constraint source_policy_enabled_requires_approval;

alter table vacancy add column if not exists closed_reason text;
alter table vacancy add column if not exists closed_at timestamptz;
alter table vacancy add column if not exists reopened_at timestamptz;
alter table vacancy add column if not exists reopened_reason text;

-- canonical_key is a candidate-generation fingerprint, not proof of identity.
-- Multiple legitimate openings may share the same company/title/location tuple.
drop index if exists vacancy_canonical_active_idx;
create index if not exists vacancy_canonical_lookup_idx
    on vacancy(canonical_key) where lifecycle_status <> 'archived';
create index if not exists vacancy_company_id_lookup_idx
    on vacancy(company_id) where lifecycle_status <> 'archived';
create index if not exists vacancy_company_domain_lookup_idx
    on vacancy(lower(company_domain))
    where company_domain is not null and lifecycle_status <> 'archived';
create index if not exists vacancy_company_name_lookup_idx
    on vacancy(lower(company_name)) where lifecycle_status <> 'archived';

create table if not exists vacancy_dedup_review (
    review_id uuid primary key default gen_random_uuid(),
    incoming_snapshot_id text not null references source_snapshot(snapshot_id),
    candidate_vacancy_id uuid not null references vacancy(vacancy_id),
    decision_reason text not null,
    confidence numeric(4,3) check (confidence between 0 and 1),
    status text not null default 'pending' check (status in ('pending','merge','create_separate','dismissed')),
    reviewed_by text,
    reviewed_at timestamptz,
    review_note text,
    created_at timestamptz not null default now()
);
create index if not exists vacancy_dedup_review_pending_idx
    on vacancy_dedup_review(status, created_at);

commit;
