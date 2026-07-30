-- SHEXON v2.2.0 -> v2.3.0
-- Phase 1 of Education/Capabilities/Task History: Basic Info account fields,
-- and the CAP/TASK activation-policy swap needed before those categories can
-- hold real, candidate-answerable elements.

begin;

-- Basic Info: contact/reachability fields, never compared against a vacancy
-- (not a Fit Dictionary category -- see PROJECT_NOTES.md). contact_preference
-- is required going forward; existing rows get a placeholder default so this
-- migration doesn't fail on data that predates the field.
alter table talent
    add column phone text,
    add column linkedin_url text,
    add column contact_preference text not null default 'email'
        check (contact_preference in ('email','phone','either','in_app_only'));

-- fit_element's own CAP/TASK check originally required activation_policy=
-- 'vacancy_activated' (the pre-Phase-1 design: CAP/TASK elements would only
-- ever activate once a specific vacancy requested that skill/task, mirroring
-- TEAM's own vacancy-gated elements). Candidate-entered skills and work
-- history need to be always answerable, independent of any vacancy -- the
-- same as PRACT/CAREER/ENV -- so this swaps the required policy to 'always'.
-- This is a targeted swap of CAP/TASK's own allow-list value, not a broad
-- relaxation: it still requires exactly one policy for CAP/TASK, and MOT's
-- (fit_element_check1, requires 'candidate_selected') and TEAM's
-- (fit_element_check2) own separate per-category constraints are untouched.
alter table fit_element
    drop constraint fit_element_check,
    add constraint fit_element_check
        check ((category in ('CAP','TASK') and activation_policy = 'always') or category not in ('CAP','TASK'));

-- New Fit Dictionary category (see src/schemas.py's Category enum).
alter table fit_element
    drop constraint fit_element_category_check,
    add constraint fit_element_category_check
        check (category in ('PRACT','CAP','TASK','TEAM','CAREER','MOT','ENV','EDU'));

commit;
