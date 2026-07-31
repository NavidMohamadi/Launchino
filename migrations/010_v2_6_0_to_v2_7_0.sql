-- v2.6.0 -> v2.7.0: talent.contact_preference loses its NOT NULL DEFAULT
-- 'email'. A default here made every fresh account's Account Settings look
-- "Complete" the instant it was created, even though the candidate had
-- never actually chosen a contact preference -- exactly the class of bug
-- this system's tri-state (answered/unknown/never-touched) convention
-- exists everywhere else to prevent. Existing rows are left untouched
-- (there is no way to distinguish a genuine past choice of 'email' from one
-- that was only ever the default -- see PROJECT_NOTES.md); this only
-- changes behavior for accounts created from now on.

begin;

alter table talent
    alter column contact_preference drop default,
    alter column contact_preference drop not null;

commit;
