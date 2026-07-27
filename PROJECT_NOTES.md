# Project notes

A running log of deliberate design decisions, known limitations, and things
flagged for later revisit — so this context doesn't get lost between sessions.

**Standing instruction**: whenever we explicitly decide something is "good
enough for now, revisit later" rather than fully resolving it, add an entry
here. This applies going forward, not just to the entries below — it's not a
one-time backfill.

Newest entries first. Each entry: what the decision/limitation/observation
is, why, and what would resolve it.

---

## 2026-07-27 — Follow-up: single-source the default category weights next time this area is touched

Not urgent, not a bug today -- a forward-looking note for whoever next touches vacancy default
weighting, prompted directly by the entry below this one.

**The problem this would prevent**: `src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS` and
`frontend/src/pages/VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS` are two independently
hardcoded copies of the same value, kept in sync only by a comment on each pointing at the other
-- nothing enforces they stay identical. This is exactly the shape of bug that already happened
once today: the CAP:30/TASK:25 default got fixed in one place and not the other (and, separately,
in a third file that turned out to be dead code -- see the entry below). Nothing stops the same
kind of silent desync happening again the next time someone updates one copy and forgets the
other.

**Suggested direction, not decided or scoped yet**: expose the default via a single backend
endpoint (the Python constant is the natural source of truth, since it's what actually drives
scraped-ingestion behavior) and have the frontend fetch it at runtime instead of hardcoding its
own copy -- e.g. a small addition to the existing `GET /fit-dictionary` response, or a new
dedicated endpoint. This was deliberately not implemented as part of today's fix: it's a real
architecture change (new API surface, a runtime fetch replacing a hardcoded constant) beyond what
"fix the default value and confirm both paths match" asked for, and deserves its own scoping
rather than being bundled in as a side effect.

**Revisit when**: the default weighting is touched again for any reason, or if this exact kind of
two-copies-drift bug recurs a second time, whichever comes first.

---

## 2026-07-27 — Correction to the same day's earlier entry, plus the default changed to equal weighting

**Correction, found while implementing a follow-up request to "confirm both paths use the same
default, not two separately-maintained values": the entry below is wrong about which file was
the real root cause.** `data/public_weight_profile.json` and its loader
(`src/public_weighting.py`'s `load_public_weight_profile()`) are **not called by any real
application code path** -- confirmed via `grep -rln "load_public_weight_profile"`, which returns
only the function's own definition and its own test (`tests/test_public_weighting.py`). Fixing
that file (as the entry below describes) had **zero effect on real production behavior**. There
are actually **three** default-weight locations, not the two assumed at the time:

1. **`src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS`** -- the *real* default for every
   scraped/ingested vacancy. Confirmed via `src/vacancy_ingestion.py:166`: it calls
   `canonicalise_raw_vacancy()` without passing `category_weights` at all, which falls through to
   this constant (`category_weights=category_weights or DEFAULT_PUBLIC_WEIGHTS`). This is what
   actually drove the 81 affected real vacancies -- was still `CAP: 30, TASK: 25` until this
   entry's fix, below.
2. **`frontend/src/pages/VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS`** -- the default
   sent by the company-direct-submission form when a company doesn't customize weights. Also
   still `CAP: 30, TASK: 25` until this entry's fix.
3. **`data/public_weight_profile.json`** -- the dead file described above. Kept up to date (now
   matching the new default below) for whoever eventually wires it in for real, and explicitly
   marked `"_status"` as unused in the file itself so a future reader doesn't assume it's
   authoritative.

**The actual fix, per this session's follow-up request**: both real locations (#1 and #2) changed
from the proportionally-redistributed profile to **equal weighting across the 5 categories with
real seeded elements** -- `PRACT: 20, TEAM: 20, CAREER: 20, MOT: 20, ENV: 20, CAP: 0, TASK: 0`.
Values kept byte-for-byte identical between the two locations, with a comment on each pointing at
the other -- there is still no runtime single-sourcing between a Python backend constant and a
bundled frontend constant, so this remains something a future change could accidentally desync;
the comments are the only guard against that today.

**Verified for real**: created a real vacancy via the company-direct path
(`company_intake.canonicalise_company_submission`) using the exact new default, confirmed
`profile.category_weights` is exactly `{PRACT: 20, CAP: 0, TASK: 0, TEAM: 20, CAREER: 20, MOT: 20,
ENV: 20}`, then ran a real match against Jordan Vance (`dab612a2-...`, a real candidate with real
answers) and confirmed `clarification_flags` contains **zero** `CAP:`/`TASK:` "no data available"
entries -- the fix from earlier today correctly does not fire when a category's weight is
genuinely `0`, only when it's nonzero with no backing data. (Test vacancy and its match rows were
deleted after verification -- this was check-only data, not meant to persist.) Separately
confirmed `src/canonical_vacancy.DEFAULT_PUBLIC_WEIGHTS` (the scraped-ingestion path) produces the
identical dict when `category_weights=None`.

**Real, and separately noteworthy**: `MOT` *did* show a "no data available for this category"
flag in that same verification run -- not a bug. `MOT` elements are `CANDIDATE_SELECTED`-activated
(only active if the candidate ranked them in their own top-5), and Jordan Vance's real profile
doesn't select any MOT factors, so MOT genuinely has zero active items *for this specific
candidate* -- same as it did before any of today's fixes, with the old weights. The flag is
working exactly as specified ("any category where weight > 0 and active_item_count == 0"): CAP/TASK
is the systemic zero-data case, a candidate not activating a category they're eligible for is a
normal per-match case, and both are honestly disclosed the same way, which is correct, not a
regression.

**Full test suite (116) passes.** `ARCHITECTURE.md` updated to reflect both the correction and the
new equal-weighting default.

---

## 2026-07-27 — CAP/TASK-weighted vacancies silently renormalize instead of scoring or erroring — RESOLVED 2026-07-27

**See the correction entry directly above this one, dated the same day** -- this entry's claim
that `data/public_weight_profile.json` was the real root cause / fix for the 81 affected real
vacancies is wrong; that file is dead code, never called by any real path. The actual fix landed
in `src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS` and
`frontend/.../VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS`. The mechanism described below
(the bug itself, and the `_flag_categories_with_no_data()` signal fix) is still accurate.

Found while cross-checking the technical handover doc (`ARCHITECTURE.md`) against the real
codebase, then confirmed as a real correctness bug, not just a doc gap.

**The bug**: `data/fit_dictionary_starter.json` seeds 41 elements across only 5 categories
(PRACT/TEAM/CAREER/MOT/ENV) -- confirmed live: `select category, count(*) from fit_element
group by category` on production returns zero rows for `CAP`/`TASK`. The `fit_element_alias`/
`fit_element_proposal` tables meant to support dynamic, vacancy-specific CAP/TASK elements
have **zero application-code references anywhere** -- fully unwired.

`src/match_engine.py`'s `aggregate_match()` (frozen since v1.2.1, must not be touched) iterates
over the *caller's configured* `category_weights`, not over what data exists. For CAP/TASK,
`items = by_category.get(category, [])` comes back empty -> `score_percent = None` -> the
`if score_percent is not None and coverage >= config.minimum_category_coverage` check on line
139 excludes that category's weight from `usable_category_weight` entirely. The overall score
is then computed and **silently renormalized** using only the categories that had real data --
no error, no warning, and `clarification_flags` never fires for this case (it only fires for
items that exist and are `unknown`; a category with *zero* items never gets there at all).

**Real-world exposure, checked directly against the live DB (not assumed)**:
- **81 of 86 real vacancies** carry `CAP: 30, TASK: 25` (55% of total weight) -- identical
  values across all 81, because this is `data/public_weight_profile.json`, the single default
  weight profile `src/public_weighting.py` applies automatically to every scraped/ingested
  vacancy without company-validated weights. **This is a systemic default, not scattered bad
  input from individual companies.**
- Only **4 real `match_run` rows** exist against any of those 81 vacancies -- all against 2
  vacancies with `company_id IS NULL` and titles containing "E2E test"/"fix-verify", matched
  against test accounts (`jordan.vance.e2etest@example.com`, `priya.nair.fix-verify@example.com`).
  **No real beta user has triggered an affected match.**
- **Zero `job_recommendation` rows** exist against any affected vacancy -- the live Job
  Discovery pipeline (the path that reaches real subscribed candidates) has never produced a
  recommendation using one of these mis-weighted vacancies.
- Pulled the actual `category_results` from the 4 test runs to confirm the mechanism, not just
  infer it: `CAP`/`TASK` both show `score_percent: null, active_item_count: 0, category_weight:
  30.0/25.0` exactly as the code predicts, with the overall score renormalized over the
  remaining 5 categories.

**Two fix options on the table, not yet decided between**:
1. **Reject nonzero weights on categories with zero real elements at vacancy-creation time.**
   Would require threading a DB-backed "which categories have real elements" check into
   `company_intake.py`/`canonical_vacancy.py` (currently DB-connection-free, framework-agnostic
   `src/` files) -- and would immediately break automatic ingestion for virtually every future
   scraped vacancy, since the *default profile itself* is the noncompliant thing; the default
   would need fixing in the same change just to keep ingestion working.
2. **Surface a clear "no data for this category" signal in the match result itself.** Fully
   computable from `CategoryResult` fields already present (`category_weight`,
   `active_item_count`, `score_percent`) in a new, small, non-frozen function running *after*
   `aggregate_match()` -- zero changes to `match_engine.py`, zero risk to the frozen boundary.
   Matches the system's existing "never silently collapse unknown into a default" philosophy
   (the tri-state model, `clarification_required` lane) better than a silent renormalization
   ever did.

**Resolution: option 2 chosen (surface a clear signal), plus the default profile fixed
immediately.**

1. **`api/matching_service.py`'s new `_flag_categories_with_no_data()`** runs immediately after
   every `aggregate_match()` call (both real call sites: `matching_service.run_match` and
   `api/job_discovery_runner.py`'s `make_deterministic_matcher`, which called `aggregate_match`
   directly and would otherwise have bypassed the fix entirely). For any category with
   `category_weight > 0 and active_item_count == 0`, it adds
   `"{CATEGORY}: no data available for this category"` into the *existing* `clarification_flags`
   list (not a new signal type, per the ask) and recomputes `lane`/`provisional` by calling
   `match_engine.py`'s own unmodified `_assign_lane()` with the updated flags -- so a
   CAP/TASK-heavy vacancy that would otherwise have looked like a confident `priority_match` now
   correctly lands in `clarification_required`. `match_engine.py` itself was not touched.
2. **`data/public_weight_profile.json`** (v2.0.0 -> v2.0.1): `CAP`/`TASK` set to `0` (from
   `30`/`25`), the freed 55% redistributed proportionally across the original five working
   categories' relative weights (`PRACT 33.34 : TEAM 22.22 : CAREER 11.11 : MOT 11.11 :
   ENV 22.22`, sums to exactly 100 -- verified via `load_public_weight_profile()`, which itself
   enforces the sum-to-100 check). This is the actual root cause fix for the 81 affected real
   vacancies' *default*, independent of the signal fix above.

**Verified for real, not just unit-tested**: re-ran `run_match()` directly against the exact two
real, already-existing test vacancies that originally demonstrated the bug (`c8328394-...`
"Robotics Software Engineer (E2E test)" / talent `dab612a2-...` "Jordan Vance", and
`dace678f-...` "(fix-verify)" / talent `5823cc9e-...` "Priya Nair"), using their genuinely
already-stored (pre-fix) `CAP: 30, TASK: 25` weights against the real live Neon DB. Both now show
`'CAP: no data available for this category'` and `'TASK: no data available for this category'`
correctly present in `clarification_flags` alongside the normal element-level flags, with
`provisional: True`. `overall_score_percent` is unchanged from the original buggy runs (83.3 and
100.0 respectively) -- correct, since this is a disclosure fix, not a rescoring fix, and these
two legacy vacancies still carry their original stored weights (not retroactively rewritten --
see below). Also confirmed the corrected `public_weight_profile.json` itself loads validly and
sums to exactly 100.0.

**What this does and doesn't fix**: the 81 already-created vacancy rows in the live DB keep their
original stored `CAP: 30, TASK: 25` weights -- `public_weight_profile.json` only affects vacancies
ingested from now on, and no data migration/backfill of existing rows was requested or performed.
Any future match against one of those 81 legacy vacancies will still compute its score the same
way it always did, but will now correctly surface the clarification flag rather than silently
renormalizing -- the safety net applies regardless of which weight configuration produced the
gap, so the legacy rows are still meaningfully protected without needing a backfill.

**Full test suite (116 tests) passes after both changes.** `ARCHITECTURE.md` updated separately
to describe the fixed behavior.

---

## 2026-07-26 — Security/GDPR hardening pass: rate limiting, input validation, GDPR technical mechanisms

Built ahead of real users onboarding. Full details in the phase's own commits;
key decisions and open items logged here.

**Deletion = anonymization, not a hard row delete -- flagged for legal
review, not silently decided.** `DELETE /candidates/{id}` and
`DELETE /companies/{id}` (`api/routers/candidates.py`,
`api/routers/companies.py`) replace directly-identifying fields
(full_name/email or contact_email, password_hash) with a tombstone value and
hard-delete the candidate's own free-text content (`talent_evidence`,
`talent_element_value`) -- but leave `match_run`/`match_summary`/
`job_recommendation`/`ai_usage_log` rows referencing the account in place,
since a true cascade delete would also destroy a company's own legitimate
record of "we ran a match against some candidate," and no FK in the schema
has `ON DELETE CASCADE` (a real hard delete would just fail on the FK
constraint). **This is a real legal judgment call about what "erasure"
means when data is shared with a third party, not an engineering decision
-- needs the user's (and likely a lawyer's) explicit sign-off**, not just
acceptance of this default.

**`ai_usage_log.error_message` no longer echoes submitted content -- RESOLVED
2026-07-27.** `api/ai_client.py`'s `_sanitize_error_for_logging()` replaces
the raw exception text logged on both a schema-validation failure (a
Pydantic `ValidationError`'s own message embeds the offending input value)
and a generic Claude API-call failure (which could in principle echo a
request fragment back, e.g. in a "bad request" error) with a safe summary:
error type/category, and for a `ValidationError`, which fields failed and
why (`loc`/`type` only, never the value). Verified directly: a real
`ValidationError` containing a sensitive test string produced a sanitized
log line with zero trace of that string. `poll_run` was also checked and is
genuinely clean -- no personal data, only per-source polling stats.

**Consent version is a placeholder.** `CONSENT_POLICY_VERSION` in
`api/models_api.py` is `"unpublished-draft-2026-07"` since no real privacy
policy text exists yet -- the mechanism (checkbox required at registration,
`consent_at`/`consent_version` recorded) is real and enforced, but the
version string needs to be replaced once real policy text is published, and
bumped every time that text materially changes.

**Rate limits are per-IP via `slowapi`, using `X-Forwarded-For`'s first
entry as the key** (`api/rate_limit.py`) -- `request.client.host` alone
would be Render/Cloudflare's own address in production, not the real
caller's. Defaults: 5/hour registration, 10/minute candidate/company login,
5/minute admin login, 20/hour on both AI-extraction endpoints. These are
reasonable starting points, not values tuned against real traffic -- revisit
once real usage patterns exist.

**SQL injection: confirmed clean.** No raw string-formatted SQL anywhere in
`api/` -- every query uses SQLAlchemy `text()` with named `:param` binds,
including the one query that takes a caller-controlled value used inside the
SQL itself (`signups_over_time`'s `granularity`), which is additionally
validated against a fixed whitelist before use.

---

## 2026-07-24 — Admin review queues (Phase 2): sponsor-match registry was never wired up; dedup-review merge is bookkeeping-only; extraction-review makes the trust-boundary gap visible, doesn't close it

Built `GET/POST /admin/dedup-review`, `/admin/sponsor-review`, and
`GET /admin/extraction-review` (`api/admin_review.py` +
`api/routers/admin_review.py`). Three real findings, not approximated:

**`ind_sponsor_registry` is not a database table and nothing ever computes a
real signal. DECISION: deliberately built-but-not-turned-on, not a near-term
follow-up** -- this is blocked on a real external data source, not on writing
more code. `src/ind_sponsor_registry.py`'s `SponsorRegistry.lookup()` is
called nowhere in the real ingestion pipeline (`company_intake.py`,
`vacancy_ingestion.py`, `job_discovery_scheduler.py`) -- only from its own
tests, against a `data/fixtures/` sample CSV with fake company names.
`vacancy.sponsorship_signal` (the real, designed-for-this storage column) has
never been populated for any real vacancy. Checked whether wiring it in today
would at least be *useful*: every real company in the database (Avular,
Sendcloud, Axelera AI, Monumental, Beyond Sports, and all test companies) has
`kvk_number = NULL` -- so even with the wiring in place, every real lookup
would only ever be able to attempt a legal-name match (never `EXACT_KVK`)
against a registry that doesn't exist yet in real form. Wiring the call in
today would produce nothing but `NO_MATCH` for every real vacancy -- work
with no observable effect, not a stepping stone.

`GET /admin/sponsor-review` still queries the real, correct storage column
(`vacancy.sponsorship_signal`) and needs no further code change to start
returning rows once this is unblocked -- confirmed via real query today: `[]`.

**Two things are both required before this is genuinely useful, not just
technically wired in** -- doing only the first is actively worse than today's
honest empty state, since it would check real vacancies against fake data and
*look* verified while testing nothing:
1. Call `SponsorRegistry.lookup()` during real vacancy ingestion, matching on
   `company.legal_name`/`kvk_number`, and persist the result to
   `sponsorship_signal`.
2. Replace `data/fixtures/ind_recognised_sponsors_sample.csv` with a real,
   periodically-refreshed IND recognised-sponsors data source (an
   acquisition/licensing/refresh-cadence decision, not a coding task) --
   real `kvk_number` values on `company` rows are also a prerequisite for
   exact matching to mean anything (every real company today has
   `kvk_number = NULL`).

**Revisit as its own standalone task** once core platform features
(dashboard, billing, deployment) are further along -- not bundled into
either of those, and not attempted piecemeal (#1 without #2, or vice versa).

**Dedup-review's "duplicate" resolution genuinely calls `vacancy_merge.py`'s
`merge_profile_fields` (unmodified) but can't refine title/description
content.** Verified for real: resolving `350cafa0-...` (a real Greenhouse
near-duplicate, confidence 0.875) correctly linked the new snapshot
(`vacancy_source_link`), left `external_job_ids` un-clobbered (the original
mapping is kept; a duplicate's ID doesn't overwrite it), and marked the
review `status='merge'` with real `reviewed_by`/`reviewed_at`/`review_note` --
queue count dropped from 12 to 11, confirmed both via the API and directly in
Postgres. What it does *not* do: full field-precedence merging needs the
incoming posting's re-parsed structured fields (title, description_text,
...), and that parsing only exists inline inside each adapter's live
`fetch()` (`src/job_sources/*.py`) -- there's no standalone "parse this
already-stored `raw_payload`" function to call for a snapshot captured in an
earlier poll cycle. Reimplementing that parsing here would duplicate
adapter-specific logic, so `merge_profile_fields` is called with
`incoming_fields={}` -- correct, not a stub, just minimal. Same limitation
means "not a duplicate" (`status='create_separate'`) records the decision but
does not materialise the incoming snapshot as its own new vacancy row today.
**Revisit if** richer review-time merging or auto-promotion to a separate
vacancy becomes a real need: extract each adapter's per-row parsing into a
standalone `parse_row(row: dict) -> RawVacancyRecord` function (a mechanical,
behavior-preserving refactor -- `fetch()` would just call it in a loop
instead of inlining), which would let both actions re-derive real content
from historical snapshots.

**Extraction-review (`GET /admin/extraction-review`) is genuinely new
visibility, not new enforcement.** It lists real `talent_element_value`/
`vacancy_element_value` rows with `source_type='ai_extraction'` (confirmed
real data: 22 candidate + 41 vacancy rows exist today) so an admin can spot-
check what's actually being confirmed. It does **not** enforce that a human
reviewed anything before confirming -- that's still the open half of the
`/workshop` trust-boundary note above (auth proves who called it, not that
review happened). It also cannot flag "submitted with zero edits" as
originally hoped: `extract-cv`/`extract-description` never persist their
draft, so there is no stored original to diff a confirmed submission
against -- this was checked and found genuinely infeasible with existing
data, not skipped. **Revisit together**: the short-lived-token idea from the
`/workshop` note (issued only by a real extraction response, required by the
confirming call) would let a *future* version of this view show a real
"was this confirmed via a reviewed draft or a raw replay" signal -- today
there is no such signal to show, for old or new submissions alike.

---

## 2026-07-24 — Admin reporting (Phase 1): three real data gaps found and closed, plus a NULL-logic bug

Building the admin dashboard's aggregation endpoints (`api/admin_reports.py`)
surfaced three genuine "no supporting data yet" gaps, each closed with the
smallest addition rather than approximated:

1. **No login timestamp anywhere.** Neither `talent` nor `company` recorded
   when someone last logged in -- needed for "active = logged in ... within N
   days." Added `last_login_at timestamptz` to both, set on successful
   `POST /candidates/login` / `POST /companies/login`, and also on
   registration (a just-registered account is trivially active, not dormant
   until its next login).
2. **No creation timestamp on survey answers.** `talent_element_value` had
   `last_confirmed_at` (optional, caller-supplied, not reliably populated) but
   nothing recording real insertion time. Added `created_at timestamptz not
   null default now()` -- existing INSERT statements don't name this column,
   so the DB default fills it with no code change needed there.
3. **`poll_run` existed in the schema from the start but nothing ever wrote to
   it.** `api/job_discovery_scheduler.py`'s `run_poll_cycle` already computes
   exactly the right data per source (`BoardValidationResult.status`/
   `job_count`/`error`) but discarded it after printing. Added
   `insert_poll_run` (`api/ingestion_store.py`) plus per-source
   created/updated counters, called once per due source per cycle. Verified
   with a real `--run-once` poll: Beyond Sports came back genuinely empty (0
   jobs), four other real boards "ok" with correct per-board job counts.
   **Honest labeling for the transition**: a source polled before this fix
   existed (6 of them, from earlier sessions) reports
   `"unknown (polled before poll_run logging existed)"`, not "ok" or
   "failing" -- `company_job_source.last_polled_at` only ever meant
   "attempted," never "succeeded," so there was no real signal to backfill.

**Bug found via real data, not a test**: `candidate_activity`'s active/dormant
query initially used `t.last_login_at >= :cutoff or exists(...)` directly.
Every one of the 11 real candidates in the DB predates the `last_login_at`
column, so it's `NULL` for all of them -- and `NULL >= cutoff` is `NULL`, not
`false`, in SQL's three-valued logic. `NULL or false` is still `NULL`, which
`count(*) filter (where not is_active)` then silently excludes from *both*
the active and dormant buckets instead of counting as dormant. First real run
returned `active_count=2, dormant_count=0` against an 11-candidate table --
caught immediately because the totals didn't add up, not because a test
caught it (no test exists for this endpoint yet). Fixed with
`coalesce(t.last_login_at >= :cutoff, false)`; after the fix, the same table
correctly reports `2 active, 9 dormant`. **Lesson**: any boolean built from a
nullable column via `OR`/`AND` needs an explicit `coalesce` unless every
branch is guaranteed non-null -- "the totals don't add up" is a cheap, real
sanity check worth running on any new aggregate query before trusting it.

---

## 2026-07-24 — `**kwargs` in the mocked Claude fakes trades a loud failure mode for a silent one

`api/tests/test_extraction_service.py` and `test_extraction_endpoints_db.py` patch
`api.ai_client.call_claude_structured` with local `fake_call_claude_structured`
functions that fully replace it (no real Claude call). Their signatures had named
the exact keyword args the real function took; twice now (`max_tokens`, then
`task`/`candidate_id`/`vacancy_id`) adding a new param to the real call sites in
`extraction_service.py` broke every one of these tests with `TypeError:
unexpected keyword argument`, since the fakes hadn't been updated to match. Fixed
by switching the fakes to `**kwargs`.

**The tradeoff, not just a fix**: named params meant *any* new keyword on a real
call site was a hard, loud test failure the moment it happened -- a forcing
function that made this exact drift impossible to miss. `**kwargs` absorbs
anything, silently. If a future parameter is added whose whole purpose is to
change behavior (e.g. a hypothetical `dry_run` flag), and the real
implementation has a bug where it's ignored or mishandled, these tests will
keep passing regardless -- there's nothing in the fakes that inspects *values*,
only that the call didn't blow up.

**Important context, not an excuse**: this loud-failure signal was always
shallow, not deep -- none of these fakes ever asserted what `task`/
`candidate_id`/`max_tokens` actually *were*, only that passing them didn't
raise. So `**kwargs` doesn't remove a real correctness check that existed
before; it removes an incidental "something changed here, go look" tripwire.
**Revisit if** a future parameter added to `call_claude_structured`/
`call_claude_text` has real behavioral stakes (not just plumbing like
`task`/`candidate_id` for logging) -- at that point, either add an explicit
assertion in the relevant test that the fake received the expected value
(`captured = {}`; fake stores its kwargs into it; test asserts after), or
accept that verifying that parameter's correctness requires a real (non-mocked)
API trial instead, same as Phase 0's `ai_usage_log` verification did.

---

## 2026-07-24 — AI usage cost logging: claude-sonnet-5's seeded price is introductory, expires 2026-08-31

Added `model_pricing` + `ai_usage_log` (Phase 0 of the admin dashboard task) --
`api/ai_usage.py`'s `DEFAULT_MODEL_PRICING` seeds `model_pricing` with real
current rates pulled from Anthropic's published pricing page (checked
2026-07-24): `claude-sonnet-5` at $2/$10 per MTok in/out, `claude-haiku-4-5-20251001`
at $1/$5. `claude-sonnet-5`'s rate is explicitly introductory pricing through
2026-08-31, after which the standard rate is $3/$15.

**Seeding is insert-if-missing, never overwrite** (`api/database.py`'s
`seed_model_pricing`), so this will not silently self-correct when the price
changes -- every `estimated_cost_usd` computed after 2026-08-31 will be too
low unless `model_pricing`'s `claude-sonnet-5` row is updated manually
(`update model_pricing set input_price_per_million = 3, output_price_per_million = 15
where model = 'claude-sonnet-5'`). **Revisit by** 2026-08-31: update that row
directly (not `DEFAULT_MODEL_PRICING`, which is only read once at first seed).

---

## 2026-07-24 — Auth: no refresh-token flow, and `GET /vacancies/{id}` will need a curated view once job-discovery recommendations are exposed

Scoped during Phase 1 of adding candidate/company/admin authentication (JWT +
bcrypt). Two deliberate scope trims, not oversights:

**No refresh-token flow.** Tokens (24h candidate/company, 4h admin) simply
expire; there is no silent renewal. An expired token means the user logs in
again. **Revisit if**: session length becomes a real UX complaint, or a
"remember me" / long-lived-session requirement shows up -- at that point add
a refresh-token table (rotating, revocable) rather than just extending access
token lifetime, since a long-lived bearer token with no revocation path is a
worse tradeoff than a short one plus refresh.

**`GET /vacancies/{id}` is being locked to company-owner-or-admin in this same
pass** (it returns the full internal profile -- `category_weights`,
`verification_status`, etc. -- not a public-safe view, and there is no
separate public job-board listing endpoint to begin with). That lockdown is
correct for company/admin use, but it will be wrong once a candidate-facing
job-discovery-recommendations endpoint exists (tracked separately -- no such
endpoint exists yet, see the "no API surface for `job_recommendation`" gap
noted during Phase 1 scoping): a matched candidate legitimately needs to see
*something* about the vacancy they were matched to, but not the full
company-internal profile. **Revisit when** that recommendations endpoint gets
built: it will need either a curated candidate-safe subset of
`CanonicalVacancyProfile` (title, company, location, description -- not
`category_weights`/verification internals) exposed via a new route, or an
explicit exception carved into `GET /vacancies/{id}`'s auth check for a
candidate who has a real `job_recommendation` row pointing at that vacancy.
Do not just open the existing endpoint back up -- that would re-expose
company-internal fields to every candidate, not just matched ones.

---

## 2026-07-23 — Fixed: extraction used non-canonical value keys; also had to raise max_tokens

Real (non-mocked) frontend E2E testing found `extract-cv`/`extract-description` reliably
extracted correct *content* but invented non-canonical JSON keys for the `value` object --
e.g. `PRACT-SPONSOR` returning `{"sponsorship_required": false}` instead of the schema's
`{"requirement": "not_required"}`. Root cause: `api/extraction_service.py`'s
`_dictionary_summary()` only ever sent `element_id`/`category`/`label` to Claude -- never
`candidate_value_schema`/`vacancy_value_schema` -- so the model had no way to know the real
key names and guessed from the label text. `value: Dict[str, Any]` on
`TalentElementValue`/`VacancyElementValue` has no per-element key validation, so these wrong
keys passed schema validation silently and only surfaced as `clarification_required` at match
time, with no error anywhere.

**Fix**: `_dictionary_summary()` now includes each element's real value schema (parameterised
by `candidate_value_schema` vs `vacancy_value_schema`), plus a new `CV_VALUE_SCHEMA_RULE` /
`VACANCY_VALUE_SCHEMA_RULE` appended instruction with worked correct-vs-wrong examples,
mirroring the existing `CV_ELEMENT_ID_RULE`/`VACANCY_STATUS_RULE` pattern. Verified with 6
real API trials (3 CV, 3 vacancy) plus a full frontend E2E pass with **zero manual
re-picking**: PRACT and CAREER category items that previously always showed
`clarification_required` now score correctly (PRACT 100%, CAREER 33.3% in the verification
run) using nothing but what the AI extracted.

**Side effect found and fixed in the same pass**: the richer per-element schemas made real
responses longer, and `api/ai_client.py`'s `call_claude_structured` had a hardcoded
`max_tokens=8192` -- confirmed via direct diagnostic (`stop_reason=max_tokens` on 3/3 real
vacancy trials) that this was truncating responses, sometimes producing a complete-looking
but *empty* `extracted_elements` list that passed validation with no error at all. Raised to
`EXTRACTION_MAX_TOKENS = 16000` in `extraction_service.py` (confirmed sufficient: real output
landed around 8500-9000 tokens across repeated trials) and added a hard check in
`call_claude_structured` that now raises `AIExtractionError` whenever `stop_reason ==
"max_tokens"`, so a truncated response can never again look like a legitimate empty result.
Note: values above ~16-20k trip the Anthropic SDK's "streaming required for operations that
may take longer than 10 minutes" guard on this non-streaming call path -- don't raise
`EXTRACTION_MAX_TOKENS` further without also switching to streaming.

**Resolved for MOT/ENV/TEAM too, confirmed by real trials, not just inferred**: the first
verification pass used a narrative CV that never stated numeric 1-5 preferences for MOT
items, so `MOT-IMPACT` correctly extracted only `{"selected": true, "example": "..."}` and
omitted `priority_rank`/`scale_id`/`preferred_min/max`/`tolerable_min/max` entirely --
omitting a nullable key vs. writing it `null` are equivalent to the comparator, so this
looked like partial compliance but was actually just "no numeric evidence in the source
text," not a key-naming bug. Ran a second, targeted verification with CV/vacancy text
written to contain explicit numeric signal for `ENV-STRUCTURE` (`ordinal_range`),
`TEAM-COLLAB-INTENSITY` (`ordinal_range`), `TEAM-HELP` (`ordinal_requirement`, a different
comparator shape from PRACT/CAREER), and `MOT-IMPACT` (`ordinal_range` with the extra
`selected`/`priority_rank` fields) -- 2 CV + 2 vacancy real trials, all four elements, both
sides. Result: every extracted `value` was an **exact key match** to its real
`candidate_value_schema`/`vacancy_value_schema` (zero invented keys, zero missing required
keys) and the numeric values themselves were consistent with the source text (e.g. "tolerate
as low as 3, no lower" -> `tolerable_min: 3`). No family-specific worked example was needed
for these comparator shapes -- the generic per-element schema embedding plus the general
"copy verbatim" instruction was sufficient on its own. Conclusion: the fix generalizes
structurally across comparator families; this is not a "revisit later" item.

---

## 2026-07-23 — `PATCH /candidates/{id}/subscription` has no auth at all — RESOLVED 2026-07-24

Added as a manual testing tool for the job discovery entitlement gate (no
Stripe/billing exists yet). Anyone who could reach this endpoint could flip
any candidate's `job_discovery_subscription` to `active`/`none`/`expired`,
`subscription_source`, and `subscription_expires_at` -- there was no
authentication or authorization check whatsoever.

**Resolved**: as part of the candidate/company/admin auth work (see the
"Add authentication" task), this endpoint now requires
`Depends(require_role("admin"))` (`api/auth.py`) -- a valid admin JWT, issued
only via `POST /admin/login` against the single env-var admin account
(`ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` in `.env`). Verified via real HTTP
calls: a non-admin (or unauthenticated) caller gets 401/403; a real admin
token succeeds. Still exists purely for manual testing of the job discovery
entitlement gate until real billing exists -- when Stripe (or similar) is
connected, this endpoint should be removed entirely (billing webhooks become
the only writer of subscription state) rather than kept around
admin-gated indefinitely.

---

## 2026-07-23 — `job_discovery_runner.py`'s recommendations have no `match_run_id`

`api/job_discovery_store.py`'s `insert_recommendation` always leaves
`job_recommendation.match_run_id` NULL. The deterministic_matcher built for
`run_full_job_discovery_cycle` (api/job_discovery_runner.py) computes
`MatchResult` objects directly (reusing `build_item_results`/`aggregate_match`)
without persisting a `match_run`/`match_item_result` row for every
(talent, vacancy) pairing it merely considers -- most pairings in a full
cross-product never become a recommendation, and persisting all of them
would be a lot of write volume for data that's discarded. Only the existing
`POST /vacancies/{id}/match` endpoint persists real `match_run` rows today.

**Consequence**: a stored `job_recommendation` shows score/coverage/lane
(denormalised onto the row itself) but has no way to drill into per-element
`match_item_result` detail the way a direct `/match` call does. The AI
explanation is generated from `MatchResult.category_results` only (no
per-item `reason` text), which the explanation prompt is told explicitly and
correctly discloses this limitation itself.

**Revisit if**: per-item drill-down for job-discovery recommendations
becomes a real product need -- would mean persisting a `match_run` per
pairing (only for pairings that become recommendations, not the full
cross-product) and threading real `item_results` into the explanation
generator alongside `MatchResult`.

---

## 2026-07-23 — `avular_careers_html` has no stable contract; it's a one-off, not a pattern

`src/job_sources/avular.py`'s `AvularCareersAdapter` is a hand-built parser
tied to avular.com's specific current page structure: exact CSS class
substrings (`articleBody`), heading hierarchy (title = nearest preceding
`<h1>` before the description container), and two specific label patterns
(English `Location:`/`Hours:`/`Employment type:`, Dutch `Locatie`/`Uren`/
`Dienstverband`). Unlike Greenhouse/Lever/Ashby, there is no versioned API
contract behind this -- it's reverse-engineered HTML.

**Consequence**: if Avular redesigns their careers page, this adapter will
most likely start raising `AvularParseError` rather than silently returning
wrong or garbled data -- that's the intended behavior (see the adapter's own
docstring), not a bug to fix reactively. But it means, unlike the three real
ATS adapters, this one needs **occasional manual re-verification** against
the live site -- there's nothing that will proactively tell us Avular
changed their markup other than this adapter failing the next time it runs.

**Also**: this was a one-off, manually-reviewed process for this one
company, not a generalized "custom HTML company" capability. Adding another
non-ATS company later means repeating the whole thing from scratch for that
company specifically -- checking for JSON-LD/hidden ATS widgets first,
reviewing robots.txt and terms of use, and writing a new dedicated,
narrowly-scoped parser -- not reusing or extending `avular.py` to cover a
second site. `data/source_registry.json`'s pre-existing `generic_company_html`
entry is not wired to any adapter and doesn't change this.

---

## 2026-07-23 — Vacancy extraction: one slow real-API trial, cause unconfirmed

During real (non-mocked) validation of the P04 vacancy-extraction prompt fix,
one trial (of several) against the real Data Scientist posting exceeded a
2-minute client timeout; a retry with a longer timeout succeeded (full
41-element coverage, no schema errors). The other trials in the same batch
completed normally within 2 minutes.

**Status: not assumed benign.** This has not been root-caused. Plausible
explanations include ordinary API latency variance, or the now-longer prompt
(base P04 text + the appended CV_ELEMENT_ID_RULE/VACANCY_STATUS_RULE
instructions + a full 41-element fit_dictionary + a long real posting)
pushing generation time up, especially now that the prompt requires
attempting all 41 elements rather than allowing an early/short response.

**If this recurs**: investigate as a latency/prompt-length issue --
consider whether `api/extraction_service.py`'s appended instructions can be
tightened without losing the fixes they encode, whether `max_tokens` in
`api/ai_client.py`'s `call_claude_structured` needs adjusting, or whether the
caller-facing timeout for `POST /vacancies/{id}/extract-description` needs to
be explicit and longer than a typical request. Do not treat a single slow
trial as resolved just because a retry worked.

---

## 2026-07-23 — Lesson: a prompt "not listening" may mean the schema is missing a field, not that the wording is weak

`prompts/P01_cv_extraction.txt` explicitly said "Do not create a new
canonical element ID. Return unmapped terms for P03/P13 and human review" --
yet real Claude API calls kept inventing element IDs (e.g. `CAP-SQL` for a
CV mentioning SQL) instead of complying, even after the instruction was made
more emphatic.

**Actual root cause**: `src/candidate_extraction.py`'s `CandidateExtractionResult`
had no field for "a real, CV-supported term with no Fit Dictionary match" --
only `unanswered_element_ids` (known IDs with no evidence) and `review_flags`
(free text). The prompt told the model what not to do, but the tool schema
it was forced to fill out gave it nowhere valid to put the finding instead.
Making the instruction louder (which was tried first) didn't fix it, because
wording was never the actual constraint.

**Generalizable lesson**: when a model repeatedly won't follow an explicit
instruction, check whether the response schema actually has a legitimate,
easy place to put the "correct" answer before assuming the instruction needs
to be stronger, more repeated, or paired with more examples. Strengthening
the wording is the second thing to try, not the first.

Fixed by adding `unmapped_terms: List[str]` to `CandidateExtractionResult`
(additive, no validation loosened) plus a strengthened, example-backed
instruction. Confirmed 3/3 real API trials with zero invented IDs afterward.

---

## 2026-07-23 — `/workshop` trust boundary is asserted, not enforced — PARTIALLY RESOLVED 2026-07-24

`POST /vacancies/{id}/workshop` stamps every row it writes
`verification_status=company_validated` (company-direct trust), on the
assumption that whatever called it was a human who reviewed the data first
-- either typed directly, or confirmed after reviewing an
`extract-cv`/`extract-description` AI draft. Originally, nothing in the
endpoint checked that a review happened, or even that the caller had any
legitimate relationship to the vacancy at all -- any caller with network
access to the endpoint got company-direct trust for free.

**Partially resolved** by the candidate/company/admin auth work: this
endpoint now requires `Depends(require_role("company", "admin"))` plus
`check_vacancy_ownership()` (`api/auth.py`), so the caller must be
authenticated as the specific company that owns this vacancy (or be admin) --
verified via real HTTP calls (a different company's token gets 403). This
closes the *outer* gap: an arbitrary/anonymous caller can no longer claim
`company_validated` trust for someone else's vacancy.

**What's still open**: auth verifies *who* is calling, not *whether a real
review happened*. A legitimate company's own valid token could still be used
to script a submission straight from an `extract-cv`/`extract-description`
draft without a human ever looking at it -- nothing distinguishes "a person
reviewed this in the browser" from "a script replayed the draft verbatim."
**Revisit when**: a real review UI matters enough to enforce that distinction
-- at that point, consider requiring the confirming call to carry a
short-lived token issued only by a genuine `extract-cv`/`extract-description`
response, so `company_validated` trust can't be claimed without the system
itself having produced a draft to review moments earlier.
