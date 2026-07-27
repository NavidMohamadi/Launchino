-- PostgreSQL starter schema for SHEXON Talent Fit + Job Discovery MVP v2.0.1.
-- Review with database, security, privacy, legal, and I-O specialists before production use.

create extension if not exists pgcrypto;

create table fit_element (
    element_id text primary key,
    category text not null check (category in ('PRACT','CAP','TASK','TEAM','CAREER','MOT','ENV')),
    label text not null,
    definition text not null,
    activation_policy text not null check (activation_policy in ('always','vacancy_activated','candidate_selected')),
    candidate_question text not null,
    vacancy_question text not null,
    candidate_value_schema jsonb not null,
    vacancy_value_schema jsonb not null,
    evidence_rule text not null,
    comparator_key text not null,
    sharing_status text not null check (sharing_status in ('internal_only','candidate_visible','employer_shareable_after_approval')),
    is_template boolean not null default false,
    version text not null default '2.0.0',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check ((category in ('CAP','TASK') and activation_policy='vacancy_activated') or category not in ('CAP','TASK')),
    check ((category='MOT' and activation_policy='candidate_selected') or category<>'MOT'),
    check ((category='TEAM' and element_id='TEAM-COLLAB-INTENSITY' and activation_policy='always') or
           (category='TEAM' and element_id<>'TEAM-COLLAB-INTENSITY' and activation_policy='vacancy_activated') or
           category<>'TEAM')
);

create table fit_element_alias (
    alias_id uuid primary key default gen_random_uuid(),
    alias_text text not null,
    canonical_element_id text not null references fit_element(element_id),
    relationship text not null check (relationship in ('exact','synonym','broader','narrower','related')),
    approved_by text not null,
    approved_at timestamptz not null,
    source_note text
);
create unique index fit_element_alias_ci_unique on fit_element_alias (lower(alias_text), canonical_element_id);

create table fit_element_proposal (
    proposal_id uuid primary key default gen_random_uuid(),
    raw_term text not null,
    proposed_element_id text,
    proposed_category text not null check (proposed_category in ('CAP','TASK')),
    proposed_label text,
    proposed_definition text,
    rationale text not null,
    status text not null default 'pending_human_review',
    proposed_by text not null,
    reviewed_by text,
    reviewed_at timestamptz,
    review_note text,
    created_at timestamptz not null default now()
);

create table talent (
    talent_id uuid primary key default gen_random_uuid(),
    full_name text not null,
    email text not null unique,
    password_hash text,
    -- Set only by a successful POST /candidates/login (api/routers/candidates.py) --
    -- needed for the admin dashboard's active/dormant definition (see
    -- api/admin_reports.py); nothing else in the codebase currently sets this.
    last_login_at timestamptz,
    profile_status text not null default 'registered',
    job_discovery_subscription text not null default 'none'
        check (job_discovery_subscription in ('none','active','expired')),
    subscription_expires_at timestamptz,
    job_discovery_campaign_opt_in boolean not null default false,
    subscription_updated_at timestamptz,
    subscription_source text
        check (subscription_source is null or subscription_source in ('manual','stripe','trial','university','company_sponsored','promotion')),
    -- GDPR: explicit consent record at registration (checkbox + timestamp,
    -- not a full legal document -- see PROJECT_NOTES.md). consent_version
    -- identifies which privacy-policy version was in effect when consent
    -- was given, since that text will change over time.
    consent_at timestamptz,
    consent_version text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index talent_job_discovery_active_idx
    on talent(job_discovery_subscription, subscription_expires_at)
    where job_discovery_subscription='active';
create index talent_campaign_opt_in_idx
    on talent(profile_status)
    where job_discovery_campaign_opt_in=true;

create table talent_element_value (
    talent_id uuid not null references talent(talent_id),
    element_id text not null references fit_element(element_id),
    value jsonb not null default '{}'::jsonb,
    value_status text not null check (value_status in ('answered','unknown','not_scored')),
    unknown_reason text check (unknown_reason in ('vacancy_not_specified','candidate_not_answered','candidate_declined','assessment_not_completed','conflicting_information','requires_verification')),
    not_scored_reason text check (not_scored_reason in ('not_top_five','not_activated_for_vacancy','out_of_scope_by_design')),
    source_type text not null,
    last_confirmed_at date,
    shareable_with_employer boolean not null default false,
    record_version integer not null default 1,
    -- Insertion time of THIS version -- last_confirmed_at above is an optional,
    -- caller-supplied "candidate reconfirmed this is still accurate" date, not
    -- reliably populated; this is needed for the admin dashboard's "submitted/
    -- updated a survey answer within N days" activity definition.
    created_at timestamptz not null default now(),
    primary key (talent_id, element_id, record_version),
    check ((value_status='answered' and unknown_reason is null and not_scored_reason is null) or
           (value_status='unknown' and unknown_reason is not null and not_scored_reason is null) or
           (value_status='not_scored' and not_scored_reason is not null and unknown_reason is null)),
    check (value_status<>'answered' or (jsonb_typeof(value)='object' and value<>'{}'::jsonb))
);

create table talent_evidence (
    evidence_id uuid primary key default gen_random_uuid(),
    talent_id uuid not null references talent(talent_id),
    element_id text not null references fit_element(element_id),
    source_type text not null,
    description text not null,
    quality smallint not null check (quality between 1 and 4),
    observed_at date,
    assessor_id text,
    shareable_with_employer boolean not null default false,
    created_at timestamptz not null default now()
);

create table company (
    company_id uuid primary key default gen_random_uuid(),
    legal_name text not null,
    display_name text not null,
    website_domain text not null,
    career_page_url text,
    country_code text,
    kvk_number text,
    contact_email text,
    password_hash text,
    -- Set only by a successful POST /companies/login (api/routers/companies.py).
    last_login_at timestamptz,
    active boolean not null default true,
    consent_at timestamptz,
    consent_version text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index company_domain_unique on company(lower(website_domain));
-- Partial (not plain unique) because most existing company rows predate any login
-- concept and have contact_email null; only rows that HAVE registered a login need
-- to be unique against each other.
create unique index company_contact_email_unique on company(lower(contact_email)) where contact_email is not null;

create table source_policy (
    source_id text primary key,
    display_name text not null,
    enabled boolean not null default false,
    terms_review_status text not null check (terms_review_status in ('approved','needs_review','partner_only','prohibited')),
    allowed_methods jsonb not null default '[]'::jsonb,
    robots_policy text not null check (robots_policy in ('respect','not_applicable_api','manual_only')),
    max_requests_per_minute integer not null check (max_requests_per_minute between 1 and 600),
    partner_approval_required boolean not null default false,
    notes text,
    reviewed_by text,
    reviewed_at timestamptz,
    updated_at timestamptz not null default now(),
    check (not enabled or terms_review_status='approved')
);

create table company_job_source (
    source_record_id uuid primary key default gen_random_uuid(),
    company_id uuid not null references company(company_id),
    source_id text not null references source_policy(source_id),
    intake_source text not null check (intake_source in ('company_direct','company_ats_feed','public_ats_api','public_company_page','partner_feed','candidate_submitted','manual_import')),
    acquisition_method text not null check (acquisition_method in ('form','api','json_ld','html','csv','webhook','manual_url')),
    board_identifier text,
    listing_url text,
    enabled boolean not null default true,
    polling_interval_minutes integer not null default 1440 check (polling_interval_minutes >= 60),
    last_polled_at timestamptz,
    next_poll_at timestamptz,
    created_at timestamptz not null default now()
);

create table poll_run (
    poll_run_id uuid primary key default gen_random_uuid(),
    source_record_id uuid not null references company_job_source(source_record_id),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'running',
    jobs_seen integer not null default 0,
    jobs_created integer not null default 0,
    jobs_updated integer not null default 0,
    error_message text
);

create table source_snapshot (
    snapshot_id text primary key,
    source_record_id text not null,
    source_id text not null references source_policy(source_id),
    source_url text not null,
    external_job_id text,
    retrieved_at timestamptz not null,
    http_status integer,
    content_type text,
    content_hash text not null,
    raw_payload jsonb not null,
    trust_level smallint not null check (trust_level between 1 and 5)
);
create index source_snapshot_external_idx on source_snapshot(source_id, external_job_id);

create table vacancy (
    vacancy_id uuid primary key default gen_random_uuid(),
    company_id uuid references company(company_id),
    company_name text not null,
    company_domain text,
    role_title text not null,
    description_text text not null,
    primary_source_url text not null,
    apply_url text,
    external_job_ids jsonb not null default '{}'::jsonb,
    intake_sources jsonb not null default '[]'::jsonb,
    acquisition_methods jsonb not null default '[]'::jsonb,
    verification_status text not null check (verification_status in ('auto_extracted','source_verified','human_reviewed','company_validated')),
    lifecycle_status text not null check (lifecycle_status in ('draft','active','updated','stale','closed','archived')),
    weighting_mode text not null check (weighting_mode in ('company_confirmed','text_derived','balanced_default')),
    weights_confirmed_by_company boolean not null default false,
    category_weights jsonb not null,
    canonical_key text not null,
    content_hash text not null,
    location_text text,
    department text,
    employment_types jsonb not null default '[]'::jsonb,
    work_mode text,
    date_posted date,
    valid_through date,
    salary jsonb,
    sponsorship_signal jsonb,
    first_seen_at timestamptz not null,
    last_seen_at timestamptz not null,
    last_material_change_at timestamptz not null,
    missing_poll_count integer not null default 0,
    closed_reason text,
    closed_at timestamptz,
    reopened_at timestamptz,
    reopened_reason text,
    record_version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (weighting_mode<>'company_confirmed' or weights_confirmed_by_company=true)
);
create index vacancy_canonical_lookup_idx on vacancy(canonical_key) where lifecycle_status <> 'archived';
create index vacancy_company_id_lookup_idx on vacancy(company_id) where lifecycle_status <> 'archived';
create index vacancy_company_domain_lookup_idx on vacancy(lower(company_domain)) where company_domain is not null and lifecycle_status <> 'archived';
create index vacancy_company_name_lookup_idx on vacancy(lower(company_name)) where lifecycle_status <> 'archived';

create table vacancy_source_link (
    vacancy_id uuid not null references vacancy(vacancy_id),
    snapshot_id text not null references source_snapshot(snapshot_id),
    is_primary boolean not null default false,
    primary key (vacancy_id, snapshot_id)
);

create table vacancy_field_provenance (
    provenance_id uuid primary key default gen_random_uuid(),
    vacancy_id uuid not null references vacancy(vacancy_id),
    field_path text not null,
    snapshot_id text not null references source_snapshot(snapshot_id),
    source_url text not null,
    extracted_at timestamptz not null,
    extraction_confidence numeric(4,3) not null check (extraction_confidence between 0 and 1),
    verification_status text not null,
    source_trust_level smallint not null check (source_trust_level between 1 and 5),
    note text
);

create table vacancy_source_conflict (
    conflict_id uuid primary key default gen_random_uuid(),
    vacancy_id uuid not null references vacancy(vacancy_id),
    field_path text not null,
    values_by_snapshot jsonb not null,
    resolution_status text not null default 'unresolved',
    resolved_value jsonb,
    resolved_by text,
    resolution_note text,
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);

create table vacancy_dedup_review (
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
create index vacancy_dedup_review_pending_idx on vacancy_dedup_review(status, created_at);
-- Re-polling unchanged content re-derives the same (incoming_snapshot_id,
-- candidate_vacancy_id) pair every cycle, since snapshot_id is a content-hash
-- fingerprint. Without this, an unresolved ambiguity would get a fresh row
-- every poll interval forever instead of one row a reviewer can act on once.
create unique index vacancy_dedup_review_pair_unique on vacancy_dedup_review(incoming_snapshot_id, candidate_vacancy_id);

create table vacancy_element_value (
    vacancy_id uuid not null references vacancy(vacancy_id),
    element_id text not null references fit_element(element_id),
    value jsonb not null default '{}'::jsonb,
    value_status text not null check (value_status in ('answered','unknown','not_scored')),
    unknown_reason text check (unknown_reason in ('vacancy_not_specified','candidate_not_answered','candidate_declined','assessment_not_completed','conflicting_information','requires_verification')),
    not_scored_reason text check (not_scored_reason in ('not_top_five','not_activated_for_vacancy','out_of_scope_by_design')),
    source_type text not null,
    source_snapshot_ids jsonb not null default '[]'::jsonb,
    extraction_confidence numeric(4,3),
    verification_status text not null default 'auto_extracted',
    item_importance smallint not null default 3 check (item_importance between 1 and 5),
    requirement_type text not null default 'important' check (requirement_type in ('critical','important','trainable','preferred','information_only')),
    trainability_window text not null default 'not_specified' check (trainability_window in ('not_trainable','one_month','three_months','six_months','longer','not_specified')),
    last_confirmed_at date,
    -- Insertion/last-write time -- mirrors talent_element_value.created_at (added
    -- Phase 1); needed so the Phase 2 extraction-review view can show/sort real
    -- submission recency instead of having no timestamp at all for this table.
    created_at timestamptz not null default now(),
    primary key (vacancy_id, element_id),
    check ((value_status='answered' and unknown_reason is null and not_scored_reason is null) or
           (value_status='unknown' and unknown_reason is not null and not_scored_reason is null) or
           (value_status='not_scored' and not_scored_reason is not null and unknown_reason is null)),
    check (value_status<>'answered' or (jsonb_typeof(value)='object' and value<>'{}'::jsonb))
);

create table match_run (
    match_run_id uuid primary key default gen_random_uuid(),
    vacancy_id uuid not null references vacancy(vacancy_id),
    algorithm_version text not null,
    weighting_mode text not null check (weighting_mode in ('company_confirmed','text_derived','balanced_default')),
    weight_configuration jsonb not null,
    threshold_configuration jsonb not null,
    public_match_provisional boolean not null default false,
    approved_by text,
    approved_at timestamptz,
    created_at timestamptz not null default now()
);

create table match_item_result (
    match_run_id uuid not null references match_run(match_run_id),
    talent_id uuid not null references talent(talent_id),
    element_id text not null references fit_element(element_id),
    value_status text not null check (value_status in ('answered','unknown','not_scored')),
    alignment text check (alignment in ('aligned','potentially_aligned','weak_alignment','misaligned','unknown')),
    score numeric(4,2),
    unknown_reason text,
    not_scored_reason text,
    reason text not null,
    requirement_type text not null,
    clarification_required boolean not null default false,
    human_review_required boolean not null default false,
    bridgeability_status text not null default 'not_applicable' check (bridgeability_status in ('not_reviewed','promising','uncertain','unlikely','not_applicable')),
    bridgeability_note text,
    primary key (match_run_id, talent_id, element_id)
);

create table match_summary (
    match_run_id uuid not null references match_run(match_run_id),
    talent_id uuid not null references talent(talent_id),
    overall_score numeric(5,2),
    overall_coverage numeric(5,2) not null,
    category_results jsonb not null,
    result_lane text not null check (result_lane in ('priority_match','promising_match','clarification_required','critical_review','lower_alignment')),
    critical_flags jsonb not null default '[]'::jsonb,
    clarification_flags jsonb not null default '[]'::jsonb,
    provisional boolean not null,
    reviewer_status text not null default 'pending',
    primary key (match_run_id, talent_id)
);

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

create table job_recommendation (
    recommendation_id uuid primary key default gen_random_uuid(),
    batch_run_id uuid references job_discovery_batch_run(batch_run_id),
    talent_id uuid not null references talent(talent_id),
    vacancy_id uuid not null references vacancy(vacancy_id),
    match_run_id uuid references match_run(match_run_id),
    result_lane text not null,
    overall_score numeric(5,2),
    overall_coverage numeric(5,2) not null,
    vacancy_verification_status text not null,
    weighting_mode text not null,
    provisional_public_match boolean not null,
    source_url text not null,
    -- source_schemas.py's JobRecommendation.explanation is a required str field
    -- (always populated by src/job_recommendations.py's build_recommendation,
    -- either from a real AI explanation or its own deterministic fallback
    -- summary); this table had nowhere to persist it until now.
    explanation text not null,
    notification_status text not null default 'not_sent',
    generated_at timestamptz not null default now(),
    unique (talent_id, vacancy_id, match_run_id)
);

create table human_review (
    review_id uuid primary key default gen_random_uuid(),
    match_run_id uuid not null references match_run(match_run_id),
    talent_id uuid not null references talent(talent_id),
    reviewer_id text not null,
    decision text not null,
    rationale text not null,
    override_details jsonb,
    created_at timestamptz not null default now()
);

-- Per-model USD pricing, seeded from api/ai_usage.py's DEFAULT_MODEL_PRICING at
-- bootstrap time (insert-if-missing, never overwritten -- see seed_model_pricing())
-- so a later manual price update here survives restarts without a code change.
create table model_pricing (
    model text primary key,
    input_price_per_million numeric(10,4) not null,
    output_price_per_million numeric(10,4) not null,
    updated_at timestamptz not null default now()
);

-- Records every real Claude API call (api/ai_client.py's call_claude_structured/
-- call_claude_text are the only two call sites in the codebase) for admin cost
-- reporting. talent_id/vacancy_id are nullable -- not every call is tied to one
-- (e.g. a future batch/system-level task might be tied to neither).
create table ai_usage_log (
    usage_id uuid primary key default gen_random_uuid(),
    occurred_at timestamptz not null default now(),
    task text,
    model text not null,
    talent_id uuid references talent(talent_id),
    vacancy_id uuid references vacancy(vacancy_id),
    input_tokens integer not null default 0,
    output_tokens integer not null default 0,
    estimated_cost_usd numeric(12,6) not null default 0,
    success boolean not null,
    error_message text
);
create index ai_usage_log_talent_idx on ai_usage_log(talent_id) where talent_id is not null;
create index ai_usage_log_vacancy_idx on ai_usage_log(vacancy_id) where vacancy_id is not null;
create index ai_usage_log_occurred_idx on ai_usage_log(occurred_at);
