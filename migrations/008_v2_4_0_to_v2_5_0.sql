-- v2.4.0 -> v2.5.0: Basic Info trim -- drop talent.linkedin_url entirely
-- (confirmed 0 of 351 real rows had it set) and remove 'in_app_only' from
-- contact_preference (there is no in-app messaging mechanism anywhere in
-- this codebase, so it was a dead-end option with no delivery path behind
-- it -- confirmed exactly 1 real row had it set, reassigned to 'email'
-- below before narrowing the CHECK, since Postgres won't let you add a
-- constraint that existing data already violates). See PROJECT_NOTES.md.

begin;

update talent set contact_preference = 'email' where contact_preference = 'in_app_only';

alter table talent
    drop constraint talent_contact_preference_check,
    add constraint talent_contact_preference_check
        check (contact_preference in ('email', 'phone', 'either'));

alter table talent drop column linkedin_url;

commit;
