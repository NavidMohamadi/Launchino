-- v2.3.0 -> v2.4.0: admin_task_run, tracking status for the manual/recurring
-- processes now triggerable from the admin dashboard ("Run now" buttons)
-- instead of only via a terminal command. This does NOT make any of these
-- processes auto-run -- every row here originates from an explicit admin
-- click (POST /admin/tasks/{task_name}/run), same as the CLI invocation it
-- replaces. See PROJECT_NOTES.md.
--
-- Distinct from poll_run (keyed per job-board source, one row per source per
-- cycle) and job_discovery_batch_run (one row per pipeline invocation,
-- already existed) -- this is the one place that tracks "is a Run-now click
-- for process X currently in flight, and what happened the last time it
-- ran," across all 5 triggerable processes uniformly.

begin;

create table admin_task_run (
    task_run_id uuid primary key default gen_random_uuid(),
    task_name text not null check (task_name in (
        'reference_refresh_ror', 'reference_refresh_esco', 'reference_refresh_croho',
        'ingestion_poll', 'job_discovery_run'
    )),
    status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    triggered_by text,
    result_summary jsonb,
    error_message text
);

-- Fast "give me the latest row for this task_name" lookup -- used both by
-- the status endpoint (one query per task_name) and the pre-trigger
-- already-running check.
create index idx_admin_task_run_lookup on admin_task_run (task_name, started_at desc);

commit;
