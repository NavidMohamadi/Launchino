-- SHEXON v2.0.1 -> v2.1.0
-- Job Discovery subscription gate, preliminary campaign signals and 14-day backfill support.

alter table talent
    add column job_discovery_subscription text not null default 'none',
    add column subscription_expires_at timestamptz,
    add column job_discovery_campaign_opt_in boolean not null default false,
    add column subscription_updated_at timestamptz,
    add column subscription_source text;

alter table talent
    add constraint talent_job_discovery_subscription_check
        check (job_discovery_subscription in ('none','active','expired')),
    add constraint talent_subscription_source_check
        check (subscription_source is null or subscription_source in
            ('manual','stripe','trial','university','company_sponsored','promotion'));

create index talent_job_discovery_active_idx
    on talent(job_discovery_subscription, subscription_expires_at)
    where job_discovery_subscription='active';

create index talent_campaign_opt_in_idx
    on talent(profile_status)
    where job_discovery_campaign_opt_in=true;

alter table vacancy
    add column last_material_change_at timestamptz;

update vacancy
set last_material_change_at = coalesce(updated_at, last_seen_at, first_seen_at, now())
where last_material_change_at is null;

alter table vacancy
    alter column last_material_change_at set not null;

create table job_discovery_batch_run (
    batch_run_id uuid primary key default gen_random_uuid(),
    run_type text not null check (run_type in ('full','preliminary_campaign','subscription_backfill')),
    started_at timestamptz not null,
    completed_at timestamptz,
    candidates_considered integer not null default 0 check (candidates_considered >= 0),
    candidates_included integer not null default 0 check (candidates_included >= 0),
    candidates_skipped integer not null default 0 check (candidates_skipped >= 0),
    vacancies_considered integer not null default 0 check (vacancies_considered >= 0),
    deterministic_matches_run integer not null default 0 check (deterministic_matches_run >= 0),
    ai_explanations_generated integer not null default 0 check (ai_explanations_generated >= 0),
    recommendations_created integer not null default 0 check (recommendations_created >= 0),
    preliminary_signals_created integer not null default 0 check (preliminary_signals_created >= 0),
    configuration jsonb not null default '{}'::jsonb
);

create table preliminary_opportunity_signal (
    signal_id uuid primary key default gen_random_uuid(),
    batch_run_id uuid references job_discovery_batch_run(batch_run_id),
    talent_id uuid not null references talent(talent_id),
    vacancy_id uuid not null references vacancy(vacancy_id),
    result_lane text not null check (result_lane in ('priority_match','promising_match')),
    overall_score numeric(5,2) check (overall_score between 0 and 100),
    overall_coverage numeric(5,2) not null check (overall_coverage between 0 and 100),
    status text not null default 'active' check (status in ('active','converted','expired','dismissed')),
    campaign_eligible boolean not null default true,
    ai_explanation_generated boolean not null default false check (ai_explanation_generated=false),
    vacancy_details_visible boolean not null default false check (vacancy_details_visible=false),
    detected_at timestamptz not null default now(),
    converted_at timestamptz,
    unique (talent_id, vacancy_id, batch_run_id)
);

create index preliminary_signal_campaign_idx
    on preliminary_opportunity_signal(talent_id, status, detected_at desc);

alter table job_recommendation
    add column batch_run_id uuid references job_discovery_batch_run(batch_run_id);
