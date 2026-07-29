-- SHEXON v2.1.1 -> v2.2.0
-- Candidate profile dashboard (per-category completion, read-only) and the
-- Premium request-and-manually-approve flow (no real payment integration).

begin;

alter table talent
    drop constraint talent_subscription_source_check,
    add constraint talent_subscription_source_check
        check (subscription_source is null or subscription_source in
            ('manual','stripe','trial','university','company_sponsored','promotion','premium_request_approved'));

create table premium_access_request (
    request_id uuid primary key default gen_random_uuid(),
    talent_id uuid not null references talent(talent_id),
    plan text not null check (plan in ('one_month','three_month')),
    status text not null default 'pending' check (status in ('pending','approved','denied')),
    requested_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by text
);

create index premium_access_request_pending_idx
    on premium_access_request(talent_id, status);

commit;
