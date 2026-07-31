-- v2.5.0 -> v2.6.0: talent.dashboard_intro_seen, tracking whether a
-- candidate has ever seen the "What Launchino does for you" dashboard
-- explainer section, so it auto-expands exactly once (on a genuinely
-- first-ever dashboard visit) and stays collapsed by default afterward --
-- distinct from overall_percent_complete === 0, which stays true on every
-- revisit until real progress is made and can't tell "first visit" from
-- "tenth visit, still nothing saved." See PROJECT_NOTES.md.

begin;

alter table talent add column dashboard_intro_seen boolean not null default false;

commit;
