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
