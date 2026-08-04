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

## 2026-08-04 — v3 Fit Dictionary redesign, Phase 7 (live E2E): mapping-code bug, candidate-side TEAM visibility

Phase 7 of the v3 redesign, against the same permanent design record (`Launchino_Fit_Dictionary_Final_v3.docx` + `Launchino_v3_Addendum.docx`). Three real findings, all found by running the thing rather than reading it.

### 1. The occupation/skill mapping "no match" bug was never about hedging language

Live E2E hit a real failure: a candidate's Task History entry "Software Engineer" came back `matched_code: null, confidence: 0.0`, even though ESCO's "software developer" was genuinely in the shortlist and the model's own reasoning named it correctly. My first hypothesis was wrong and worth recording as wrong: I assumed the prompts' "HARD RULE" (added earlier after the real "Excel" → "KDevelop" at 0.9 over-confidence bug) was over-triggering on hedge-adjacent words like "closest match", and had overcorrected into false negatives.

Reproducing the raw pre-`_to_result` response disproved that. The model's judgement was already correct and confident — `confidence: 0.95`, `matched_label: "software developer"` — but `matched_code` came back as **`'2512.3'`**, an ISCO occupation-group code from the model's own training knowledge, instead of the shortlist item's `uri`. `_to_result`'s `valid_codes` backstop then did exactly its job and discarded it as invented, zeroing the confidence. So the honest diagnosis is: this was a **code-format/instruction-following bug, not a confidence-calibration bug**, and the null was the safety net working correctly on top of a bad input — the failure was upstream of the rule I initially blamed.

Fixed by making the required format explicit where the model actually reads it: a real `description` on `MappingResponse.matched_code` (`src/mapping_schemas.py`) saying the value must be copied character-for-character from the chosen option's own identifier field and never substituted with a code from another classification system (ISCO/SOC/NAICS) however standard it feels — plus the same instruction in both prompts' OUTPUT sections. Verified against the real API: "Software Engineer" → `software developer` at 0.95 with the correct ESCO uri, while the original over-confidence guard still holds — "Excel" still correctly returns null at 0.1, reasoning that no shortlist item denotes spreadsheet skills.

I also reworded the HARD RULE in both prompts to judge on *meaning* rather than wording ("this is about your JUDGEMENT, not your WORDING") with worked both-direction examples. That is a defensible improvement on its own and it is now consistent with the observed behaviour, but it should be recorded plainly: **it was not the fix for this bug**, and the original rule was not the cause.

### 2. Candidate-side TEAM capability elements were unreachable — the mirror of the Phase 6 addendum gap

The Phase 6 addendum fixed the *vacancy* side of the "no manual activation path" gap. Phase 7's live run surfaced the exact mirror image on the candidate side: "How you work" rendered only `TEAM-COLLAB-INTENSITY`. `CategorySurveyPage.jsx` showed non-MOT elements only when `e.active`, but `active` for a `vacancy_activated` element is a fact about a *vacancy*, and the candidate's general profile has no vacancy context to resolve it — so `e.active` is structurally always false there. Net effect: **no candidate could ever self-rate any of the 6 TEAM capability elements**, and the vacancy side had nothing to compare against.

Fixed per the user's explicit direction, and deliberately not by weakening activation: `vacancy_activated` elements are now always visible on the candidate's own profile, while the vacancy side keeps its activation gating exactly as built in the Phase 6 addendum. This mirrors how CAP-SKILLS and MOT already work — the candidate answers proactively once, and the vacancy decides which elements actually get *scored* for a given role. `TEAM-EVIDENCE` (same `vacancy_activated` policy, `unscored`, the free-text companion to those six) was unreachable for the identical reason and is included in the same fix.

While making them visible, a latent schema drift became reachable and was fixed: `OrdinalRequirementCandidate` rendered an "Example" text field, but `example` exists only in these elements' `vacancy_value_schema`, never their `candidate_value_schema` — the candidate's illustrative example is `TEAM-EVIDENCE`, one answer covering all six, not six repetitions of the same ask. It had never actually written off-schema data only because the editor was unreachable candidate-side. Removed.

### 3. Verified end to end, both halves

Candidate half through the real UI: all 8 TEAM elements render and submit; stored payloads are clean and schema-conformant (`{"level": N}` only, no stray `example`), with deliberately varied self-ratings (COMM 4, HELP 4, FEEDBACK 3, COORD 2, CONFLICT 1, SHARED-OWNERSHIP 1, COLLAB-INTENSITY 4) so shortfalls would be visible rather than uniform. The mapping fix was also confirmed through the real UI, not just the script — the Task History entry now shows "Matched occupation: software developer".

Match half via a real `run_match` against that real candidate data, with a vacancy activating only 3 of the 6 (COMM required 3, COORD 2, CONFLICT 4). Result — exactly the intended behaviour:

- `TEAM-COMM` (req 3 vs self-rated 4) → `aligned`, 3.00
- `TEAM-COORD` (req 2 vs 2) → `aligned`, 3.00
- `TEAM-CONFLICT` (req 4 vs 1) → `weak_alignment`, 0.75 — a real shortfall, correctly detected
- `TEAM-HELP` / `TEAM-FEEDBACK` / `TEAM-SHARED-OWNERSHIP` → `not_scored` / `not_activated_for_vacancy`, **despite the candidate having answered all three**

That last line is the whole point: proactive candidate answers do not leak into scoring for a role that never asked for them. TEAM category coverage 100%, score 76.2. The candidate's real UI-entered PRACT answers also scored correctly against that vacancy (SPONSOR/WORKMODE/WORKTYPE all `aligned`; unset ones correctly `unknown` / `vacancy_not_specified`).

Full backend test suite: 235 passed.

**Honest scope caveat on how the vacancy half was driven.** The candidate half was done entirely through the real browser UI. The vacancy half was not: it was built through the same canonicalisation + persistence code path the `POST /vacancies` endpoint uses, then matched via the real `run_match`, because driving the vacancy workshop in the browser requires authenticating as the company and I don't enter credentials. The vacancy-side activation *UI* was already verified live in the Phase 6 addendum, so what this run adds is verification of the *engine's* gating against real candidate data — which is the part that was genuinely unproven. A fully browser-driven company walkthrough is still worth doing once, with the user logged in.

### Deferred, out of scope here: a real per-vacancy application / follow-up flow

Both activation gaps (this one and the Phase 6 addendum) are symptoms of a bigger absence worth naming as legitimate future work rather than patching around again: **there is no per-vacancy application or follow-up flow.** Today a candidate fills in one general profile and a company fills in one general vacancy, and matching joins them. What does not exist is the step where a candidate engages with a *specific* role and is asked the things that only make sense in that context — e.g. answering the TEAM capabilities *that this vacancy activated*, confirming or correcting an AI-proposed ESCO mapping for this application, or supplying a role-specific example.

That would make activation meaningful in both directions instead of being a scoring-time-only concept, and would let the profile stay short while still collecting depth where it matters. It is a genuine product design decision (when is a candidate asked? is it blocking? does it change the stored value or layer on top of it?), not a UI tweak — deliberately not attempted here.

### Cleanup: done

Phase 7 test data has been removed from the shared Neon DB (user-authorised, after the verification above was complete): candidate "Phase 7 Real Candidate" (`9614bdef-…`), company "Launchino Live Test Co" (`80647594-…`), and all five "Phase 7 TEAM Activation Test" vacancies, plus every referencing row — 212 `match_item_result`, 50 `vacancy_element_value`, 18 `talent_element_value`, 4 `match_run`, 4 `match_summary`, 3 `ai_usage_log`. Verified zero remaining; no other account or vacancy touched (the company owned no non-test vacancies, asserted in-transaction before deleting).

Deliberately a **hard delete, not** the production `DELETE /candidates/{id}` path. That endpoint anonymises to a tombstone rather than deleting, because for a real user a company's own match records must survive erasure (see its docstring and the security-hardening entry). That reasoning does not apply to synthetic scratch data, where leaving tombstoned rows and orphan match history in a live shared DB would be strictly worse than removing them. `ai_usage_log` rows were included so admin cost reports don't report AI spend attributed to an account that no longer exists — worth noting since that table is otherwise business/billing telemetry, not user content.

Every FK involved is `ON DELETE NO ACTION`, so the deletion ran in one transaction in explicit dependency order (match children → talent/vacancy children → parents), re-deriving the target ids inside the transaction instead of trusting hardcoded ones.

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 6 addendum: TEAM activation checkbox UI on the vacancy workshop

Follow-up to the Phase 6 entry directly below, requested explicitly rather than deferred: a minimal UI for the structural gap that entry flagged (no way anywhere for a company to manually activate a `vacancy_activated` element), scoped specifically to the 6 TEAM capability questions so Phase 7's end-to-end test can be genuinely real instead of forcing activation through a direct API call.

`VacancyWorkshopPage.jsx` now tracks its own `activatedIds` state and passes it into `useFitDictionary({ vacancyActivatedIds: activatedIds })`, mirroring `CategorySurveyPage.jsx`'s MOT checkbox pattern (the existing candidate-side precedent for the same `activation_policy` concept) rather than inventing a new one. Any element with `activation_policy === 'vacancy_activated'` now always renders a checkbox (regardless of `e.active`, since showing it *is* the point when nothing has activated it yet), with the full tri-state question revealed only once checked. Checking a box seeds `{activated: true}` into that element's answer value immediately — the same fix `toggleMot` needed in Phase 5, since `build_item_results` reads `value.activated` from the *stored* payload, not from any page-local state. Extraction results are also synced into `activatedIds` when they themselves set `activated: true`, so an AI-activated element doesn't render as an unchecked box sitting above its own already-answered question.

Verified live: registered a fresh company, confirmed all 6 checkboxes render (with their real label + definition text) initially unchecked and answerless; checked two (`TEAM-COMM`, `TEAM-CONFLICT`), confirmed their full editors appeared with the seeded `required_level: 2` default; submitted; confirmed in the database that exactly those two persisted with `{"activated": true, "required_level": 2}` and the other four were correctly absent (never activated, never submitted). No cap on how many can be activated — the `selected_priority_rank: 1..4` field removed in the main Phase 6 entry hinted at an original intent to cap at 4, but nothing in the current comparator or activation logic enforces or needs one, so this stays genuinely minimal rather than guessing at a constraint.

Full backend test suite: 235 passed (unchanged — frontend-only change).

Same phase breakdown as before: Phase 7 (live E2E with real accounts and a real match run) is next, still pending the user's go-ahead.

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 6 (vacancy-side wording): complete

Follow-up to Phases 1-5 below. Same permanent design record. Scope per the user's own framing: "verify existing text, don't assume" — an audit of every `vacancy_question`/`vacancy_value_schema` touched by this redesign, not a re-litigation of already-settled design decisions.

**The 6 reworked TEAM capability elements' vacancy side was genuinely stale, not just cosmetically.** Phase 1 rewrote the candidate side to Family 1 capability framing but deliberately left the vacancy side untouched ("Phase 6 territory" — see that entry). Checking it now: `vacancy_question` still asked "How important is timely team communication in this role, and what behaviour would demonstrate success?" — a qualitative importance/behaviour question — while the schema underneath it wants a numeric `required_level` for Family 1's shortfall formula. Rewrote all 6 to mirror their candidate-side question in third person ("How consistently must someone in this role keep teammates informed..."). Also found `"required_level": 0` was a literal placeholder integer, not a documentation string (pre-existing since before this redesign), and `selected_priority_rank` was dead schema cruft — confirmed via a repo-wide grep that it's never read by any comparator, matching, or frontend code anywhere — removed both.

**A real scale mismatch found while touching that same schema, not assumed away**: `candidate_value_schema` documented `"integer 1..5"` (written by me in Phase 1), but the actual `Stepper04` control both TEAM-* elements and `TASK-YEARS` share (`frontend/src/components/valueEditors/index.jsx`) has always rendered `min={0} max={4}` — a real, pre-existing UI range, not something I'm free to assume matches the doc string. Since both candidate and vacancy sides already consistently use 0-4 (the shortfall formula only cares about relative distance, not the absolute scale), correcting the *documentation* to `"integer 0..4"` was the safe, accurate fix — changing the real UI range would be a separate, bigger decision (see the TASK-YEARS flag below).

**New EDU vacancy-side control, not previously built**: `education_field_requirement` (`required`/`preferred`/`open` — added to the schema in Phase 1, read by `score_education_history` since Phase 2) had no UI anywhere; a company had no way to ever set it, so every vacancy silently defaulted to `"open"` (field ignored entirely) without ever surfacing that as a real choice. Added an explicit `Select` in `RequiredEducationVacancy` with real explanatory option text ("Required -- a field mismatch rules the candidate out", etc.), left unset by default rather than auto-seeded — this is a genuine business decision a company should make deliberately, not a slider-style control where "no interaction" has no sensible meaning (see Phase 5's `useSeedDefaults` reasoning for why those two cases are handled differently). Verified live: selected "Required", submitted, confirmed `{"education_field_requirement": "required"}` in the database.

**Verified the TEAM wording live too, but had to work around a real, pre-existing gap to do it**: registering a fresh company and using "skip to manual" showed only `TEAM-COLLAB-INTENSITY` (Family 2, always-active) — none of the 6 rewritten capability elements appeared at all, because `GET /fit-dictionary`'s `active` field is the *resolved* `is_activated()` state, and `VacancyWorkshopPage.jsx` never passes `vacancy_activated_ids` on the manual-entry path. Confirmed via a repo-wide grep: **there is no UI anywhere, for any `vacancy_activated` element, for a company to activate it manually** — not a scoped-down version of a feature, a complete absence. This is the same root cause as the MOT gap flagged in Phase 5's entry, but total rather than partial (MOT at least has a candidate-side selection precedent to model a fix on; TEAM has no equivalent anywhere). Verified the wording/schema fix is correct anyway by calling `GET /fit-dictionary?vacancy_activated_ids=...` directly to force `active: true`, and confirmed the shared `OrdinalRequirementVacancy` editor renders correctly for this shape (already proven working for the always-visible `TASK-YEARS` on the same page, since it's the same generic component). These two findings (MOT + TEAM) are really one structural gap, not two: no `vacancy_activated`/`candidate_selected` element has a real vacancy-side manual-activation path outside of AI extraction happening to set the flag. Worth a real, dedicated design decision — not a Phase 6 wording fix.

**Flagged, not fixed — a real, likely-blocking bug, but pre-existing and out of this phase's scope**: `TASK-YEARS` shares the exact same `Stepper04` (0-4) editor as the TEAM capability elements, meaning a company currently has no way to require, say, "5 years of experience" for a senior role — the input is hard-capped at 4. This predates this whole v3 redesign (the shared editor registry is keyed by `comparator_key` alone, and `TASK-YEARS` was already on `ordinal_requirement` before Phase 1 started) and isn't something this redesign made worse, but it's a real, concrete, live-blocking issue for actually using the product, surfaced by this same audit. Properly fixing it means giving `TASK-YEARS` its own `comparator_key`/editor pair distinct from TEAM's — a real backend + frontend change, not wording — so left for a dedicated task rather than folded into this one.

Full backend test suite: 235 passed (unchanged — this phase's changes were dictionary content + frontend, both exercised live rather than via new automated tests, matching the "wording audit" nature of the work).

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 7 (live E2E with real accounts and a real match run).

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 5 (frontend): complete

Follow-up to Phases 1-4 below. Same permanent design record. Builds the value editors flagged as missing in the Phase 4 entry's browser verification ("No editor registered for comparator_key...", shown for every v3 element on both survey pages).

**Five new editor pairs added to `frontend/src/components/valueEditors/index.jsx`** (registered in `VALUE_EDITORS`, same registry pattern as every prior category):
- `ordinal_distance` (single 1-5 slider both sides) — 9 ENV + 4 new ENV + 6 RIASEC + `TEAM-COLLAB-INTENSITY` = 20 elements.
- `motivation_preferred_minimum` (preferred + minimum-acceptable sliders candidate-side, single actual slider vacancy-side) — 13 MOT elements.
- `esco_occupation_pick` (plain-language search-and-pick against real ESCO occupations, ESCO codes never shown to the user; candidate side adds `still_exploring`/`open_to_adjacent` checkboxes) — `CAREER-PRIMARY-ROLE`/`SECONDARY-ROLE`.
- `nace_industry_overlap` (repeatable dropdown picker against the 21 NACE sections) — `CAREER-INDUSTRIES`. Needed a new backend endpoint, `GET /reference/nace-sections` (`api/routers/reference.py`) — `list_nace_sections()` already existed server-side from Phase 1 but was never exposed over HTTP.
- `unscored` (plain free-text textarea, candidate side only) — `CAREER-NARRATIVE`, `CAREER-DEVELOPMENT`, `TEAM-EVIDENCE`. `VacancyWorkshopPage.jsx` now filters `comparator_key === 'unscored'` out of its rendered element list entirely rather than showing an editor with nothing to answer — matching_service.py already excludes these from real matching (Phase 2), and their `vacancy_value_schema` is genuinely empty.

**Real bug found via live browser verification, not by inspection — and it's bigger than cosmetic**: submitted the ENV survey page without touching any of the 13 new sliders (all showing a visible default of "3") and got `values_stored: 0`. Root cause: `<input type=range>` always renders *some* number — there's no meaningful empty state the way a `Select` has "-- choose --" — but `CategorySurveyPage`/`VacancyWorkshopPage` only include an element in the submission once something has called `onChange` for it. A candidate/company who accepts what's already shown and submits without dragging the slider silently loses that answer. This affects every slider-based editor, not just the three new ones — including the pre-existing `ordinal_requirement` editor (TEAM capability elements + `TASK-YEARS`), fixed in the same pass for consistency. New `useSeedDefaults()` helper: each slider editor now calls `onChange` once on mount if its value is still empty, so the default shown is the default submitted. Re-verified after the fix: the same untouched ENV page now reports `values_stored: 13`, confirmed correct in the database (`{"level": 3}` for all 13).

**A second real, pre-existing bug found and fixed in the same file while already there**: `CategorySurveyPage.jsx`'s MOT checkbox handling (`toggleMot`) never included `selected`/`priority_rank` in the submitted value — it only tracked selection in page-level state. `build_item_results` (`api/matching_service.py`) resolves `CANDIDATE_SELECTED` activation via `value.get("selected", False)` on the *stored* value, so a checked-but-otherwise-untouched MOT element would have silently resolved `not_scored`/`not_top_five` at match time regardless of what the candidate actually selected. Fixed by seeding `{selected: true, priority_rank: n}` into the value the moment a MOT checkbox is checked (not just an empty `{}`); the new motivation editor spreads `...value` so it composes correctly with the slider default-seeding above. Verified live: checked 3 MOT priorities (including `MOT-CHALLENGE`) without any further interaction, submitted, confirmed all 3 persisted with `selected: true` and sequential `priority_rank` (1, 2, 3) plus the seeded `preferred_level`/`minimum_acceptable_level`.

**Verified live in a real browser end to end, not just that nothing crashes**: registered fresh candidate + company accounts; confirmed all 13 ENV sliders, all 3 tested MOT priorities (`MOT-LEARN`, `MOT-STABILITY`, `MOT-CHALLENGE`), and every CAREER element (ESCO search against the real `/reference/occupations` endpoint — picked "software developer", got a real `esco_uri` back; NACE dropdown against the real 21-section list — picked "Information and communication" / code `J`; free text for `CAREER-NARRATIVE`/`CAREER-DEVELOPMENT`) round-tripped correctly through submission into the actual database, on both candidate and vacancy sides. `still_exploring`/`open_to_adjacent` being absent from the stored value when left unchecked was checked and confirmed harmless — `score_occupation_pick` reads them via `.get()`, so a missing key and an explicit `false` behave identically (unlike the numeric slider case, where a missing key correctly resolves `UNKNOWN` rather than defaulting to something fabricated).

**Known, pre-existing limitation confirmed (not introduced here, not fixed here)**: the vacancy workshop's "skip to manual" path never shows MOT elements at all, because `GET /fit-dictionary`'s `active` field is the *resolved* activation state (`is_activated()`), and MOT's `CANDIDATE_SELECTED` policy always resolves `false` with no candidate in the picture — matching this page's own existing comment ("vacancy side cares about ALWAYS + VACANCY_ACTIVATED elements"). MOT elements only appear on the vacancy review screen when pre-populated via AI extraction (which doesn't go through this activation gate). A vacancy that skips extraction currently has no way to manually answer a MOT element's `actual_level` for a priority no candidate has selected yet. Real, structural, worth a future decision — not something this phase's scope (building missing editors) should silently paper over.

Full backend test suite: 235 passed (unchanged from Phase 4's count — only the new `GET /reference/nace-sections` endpoint was backend-side, exercised live rather than via a new automated test, since it's a two-line pass-through mirroring `isced-fields`' already-tested pattern exactly).

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 6 (vacancy-side wording — verify existing text, don't assume), Phase 7 (live E2E with real accounts and a real match run).

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 4 (not_scored/unknown labeling + AI-extraction safeguard): complete

Follow-up to Phases 1-3 below. Same permanent design record. Two independent pieces, both explicitly called out as "FINAL DECISION" items in the v3 spec's labeling/safeguard section.

**1. Four-label not_scored/unknown matrix, split by side.** `frontend/src/components/TriStateAnswer.jsx`'s toggle previously showed the same "Don't know"/"Not applicable" text regardless of which side (`candidate` vs `vacancy`) was answering, even though the `side` prop was already correctly threaded through from both `CategorySurveyPage.jsx` and `VacancyWorkshopPage.jsx`. Added `unknownLabel(side)`/`notScoredLabel(side)`: candidate side reads "Don't know"/"Not applicable to me"; vacancy side reads "Not yet known"/"Not relevant to this role" — a company simply not having answered yet is a genuinely different situation from a role not needing something at all. While in the file, also humanized the reason-code dropdowns (`REASON_LABELS`), which were previously showing raw snake_case enum values (`candidate_not_answered`, `vacancy_not_specified`, etc.) directly to users — not explicitly called out in the spec's labeling decision, but the same class of problem in the same component, cheap to fix while already there.

Verified live in a real browser on both sides (not just read from source): registered a fresh candidate, confirmed the ENV survey page's toggle reads "Answered / Don't know / Not applicable to me"; registered a fresh company, created a vacancy, confirmed the vacancy workshop review screen's toggle reads "Answered / Not yet known / Not relevant to this role" for the same elements. Both test accounts were cleaned up afterward (this session's own fresh residue, not ambiguous data).

**2. AI-extraction safeguard.** Confirmed a real gap by reading the actual code, not assuming: `extraction_service.py`'s `VACANCY_STATUS_RULE` (and CV extraction's equivalent instructions) told the model how to choose `value_status`/`unknown_reason`/`not_scored_reason` entirely through prompt wording, and `submit_candidate_survey`/the vacancy workshop submit endpoint both store whatever `value_status` the client sends after only checking *internal* consistency (`TalentElementValue`/`VacancyElementValue`'s own reason-pairing rules) — never independently re-deriving whether `not_scored` is actually correct given the element's real activation policy. Nothing previously closed the loop the spec calls out: "the extraction model may only propose a value; the activation resolver (code, not the LLM) makes the final not_scored/unknown decision."

New `resolve_extracted_value_status()` (`src/activation.py`, alongside the existing `is_activated`/`resolve_scope`) is that resolver, adapted for the one-sided extraction context (a CV or vacancy-description extraction only ever has one side's data, unlike real match-time resolution which has both): `not_scored` is only ever structurally valid for the ONE activation policy the side in question can actually decide for itself — `CANDIDATE_SELECTED` via the candidate's own proposed `selected` flag, `VACANCY_ACTIVATED` via the vacancy's own proposed `activated` flag (the other policy's not_scored condition is a fact only the *other* side could ever assert — e.g. a vacancy extraction has no way to know whether some future candidate will pick a given MOT priority as a top-five, so `not_top_five` is never a vacancy-side call to make). Every other case is corrected to `answered`/`unknown` purely from whether real data is present, regardless of what `value_status` the model itself proposed; if the model's own proposal already agrees with that correction, its more specific `unknown_reason` is preserved rather than replaced with a generic fallback.

Wired into `api/extraction_service.py`'s `run_cv_extraction`/`run_vacancy_extraction` via a new `_apply_extraction_activation_safeguard()` post-processing step — runs on every extracted element after the model returns, before the result reaches the review screen, so a human reviewer sees an already-corrected draft rather than a raw, unverified guess.

Full backend test suite: 235 passed. 9 new unit tests in `tests/test_activation.py` covering every branch of `resolve_extracted_value_status` (candidate-selected/vacancy-activated force-to-not_scored, the reverse correction when active, always-active elements, motivation elements never getting not_scored on the vacancy side, specific-reason preservation), plus 4 new integration tests in `api/tests/test_extraction_service.py` confirming the safeguard is actually wired into `run_cv_extraction`/`run_vacancy_extraction` end to end, not just correct in isolation.

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 5 (frontend — including building the missing value editors for `ordinal_distance`/`esco_occupation_pick`/`nace_industry_overlap`/`unscored`, confirmed still absent via this same browser verification: "No editor registered for comparator_key..." shown for every v3 element on both survey pages), Phase 6 (vacancy-side wording), Phase 7 (live E2E with real accounts and a real match run).

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 3 (reset/migrate existing TEAM/MOT/ENV data): complete

Follow-up to Phases 1-2 below. Same permanent design record. This phase migrates the 9 pre-existing `ENV-*` elements, all 12 pre-existing `MOT-*` elements, and `TEAM-COLLAB-INTENSITY` off the old 4-value `ordinal_range` format onto the Family 2 (`ordinal_distance`)/Family 3 (`motivation_preferred_minimum`) formats Phase 2 already implemented — closing the "temporary, documented split" both prior entries called out. No new comparator code was needed; these 22 elements now simply route through the exact same functions the 10 new elements already used.

**Real-data finding, checked before touching anything (same discipline as Phase 1's CAREER migration)**: every one of the 72-73 "answered" rows found for the 9 ENV elements and `TEAM-COLLAB-INTENSITY` traced back to `completion-test-*@example.com` accounts — confirmed via the `full_name`/email pattern to be leftover residue from this session's own `api/tests/test_candidate_completion.py` runs against the shared live DB, not real production candidates. MOT had almost no answered data at all (2 real rows total, for `MOT-IMPACT`/`MOT-COLLABORATION`, and those 2 predate even the current `ordinal_range` schema — `{"example"/"text", "selected"}` only, no numeric fields whatsoever). This meaningfully lowered the stakes versus Phase 1's genuine-user-data situation, but the same real conversion was still applied rather than silently discarding anything recognizable.

**Conversion rules applied** (`talent_element_value`/`vacancy_element_value`, real UPDATE/new-version-INSERT against the live DB, matching the established "new version row, never edit in place" pattern):
- Candidate `level`/`preferred_level` = the rounded midpoint of the old `preferred_min`/`preferred_max` range, clamped to 1-5.
- MOT's `minimum_acceptable_level` = the old `tolerable_min` directly — not an arbitrary choice: "the lowest I'd still accept" is exactly what `tolerable_min` already meant, so this is a genuine semantic correspondence, not a fabrication.
- Vacancy `required_level`/`actual_level` = the old `actual` value directly (already a single 1-5 number in the old schema) — a lossless rename, no judgment call needed.
- The 4 MOT rows with no numeric fields at all (`MOT-IMPACT`/`MOT-COLLABORATION`, predating even the old schema) were left untouched — there was nothing recognizable in them to honestly convert, and inventing a number would be a fabrication, not a migration.

**Real migration results**: 720 candidate rows migrated (72-73 talents × 10 elements: 9 ENV + `TEAM-COLLAB-INTENSITY`), 1 skipped as unrecognizable/malformed; 0 MOT candidate rows migrated (4 skipped, all predating the schema, as above); 2 ENV/TEAM vacancy rows migrated; 6 MOT vacancy rows migrated (all converted to `"not_specified"`, since none of the real vacancies had stated an actual value in the first place).

**Real bug found and fixed via this same real-data check, not by inspection alone**: running a live match against the migrated data crashed with `TypeError: unsupported operand type(s) for -: 'int' and 'str'` — `score_ordinal_distance` and `score_ordinal_requirement` (both from Phase 2) only checked for `None`, not the literal string `"not_specified"`, which is a real, documented vacancy value and exactly what several of the real migrated rows now legitimately contain. Fixed both (and hardened `score_motivation_preferred_minimum`'s equivalent check from an `==` comparison to a type check) to treat any non-integer value as "not specified" → `UNKNOWN`, not a crash. Added 2 regression tests reproducing the exact crash inputs.

`tests/test_survey_contracts.py`'s `test_environment_and_motivation_use_five_point_scales` was simplified to assert the format uniformly across all ENV/MOT elements (plus `TEAM-COLLAB-INTENSITY`) now that the temporary split from Phase 1/2 no longer exists. `api/tests/test_candidate_completion.py`'s fixtures updated to submit the new `{"level": N}` shape for these elements instead of the old range shape.

**Known, accepted gap until Phase 5 (frontend)**: the live frontend's `OrdinalRangeControl` still renders the old 4-slider UI for these 22 elements and would submit old-shaped payloads. This is not a crash — value payloads aren't strictly schema-validated at submission time, so an old-shaped submission is still accepted and stored, just resolves to `UNKNOWN` under the new comparator until Phase 5 ships the matching single-1-5-button UI. This is the same kind of temporary backend-ahead-of-frontend gap every prior phase in this redesign has had; flagged here for completeness, not a surprise.

Full backend test suite: 223 passed (0 failed) after the fix, run twice for confirmation. Real match run against the live DB's actual dictionary (56 elements, all 22 migrated elements included) confirmed no crashes and correct `UNKNOWN` resolution for the real (all-`"not_specified"`) vacancy data available; the underlying formulas themselves were already directly verified with real integer inputs in Phase 2's unit tests, and Phase 3 only changed which dictionary elements route through that same, already-proven code path.

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 4 (`not_scored`/`unknown` labeling + AI-extraction safeguard), Phase 5 (frontend), Phase 6 (vacancy-side wording), Phase 7 (live E2E with real accounts and a real match run).

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 2 (real comparator formulas): complete

Follow-up to Phase 1 below. Same permanent design record (`Launchino_Fit_Dictionary_Final_v3.docx` + `Launchino_v3_Addendum.docx`). This phase implements the 5 scoring families' real formulas, replacing the safe stub branches Phase 1 left in `comparators_dispatch.py`.

**Real architectural finding, resolved without pausing (squarely in-scope per the task's own charter that `match_engine.py`/comparators are explicitly not frozen here)**: the pre-existing scoring pipeline only supported 4 discrete `Alignment` buckets (`ALIGNED`/`POTENTIALLY_ALIGNED`/`WEAK_ALIGNMENT`/`MISALIGNED` → 100/66.7/33.3/0%), but Families 1-3's formulas need finer continuous gradients (Family 1's shortfall 1/2/3/4 → 75/50/25/0%; Family 2's distance 0-4 → 100/80/60/40/20%; Family 3's gradients are finer still). Resolution: `ItemResult.score` was already an unconstrained `Optional[float]` in `[0,3]` (`src/schemas.py`), so no schema change was needed — `make_item_result` (`src/match_engine.py`) now accepts an optional `score_percent` override; when a comparator supplies one, it becomes the authoritative score, and `alignment` becomes only a *display* bucket derived from that percent via a new `alignment_bucket_for_percent` helper (boundaries at the midpoints between the 4 old anchor values, so an unchanged old-style exact-bucket result still labels identically to before). Every pre-existing comparator_key is untouched — `score_percent` is `None` for all of them, so `make_item_result` derives the score from `ALIGNMENT_SCORE[alignment]` exactly as it always did.

**Two live production gaps found and fixed**: Phase 1 assigned `comparator_key: "ordinal_distance"` (10 new ENV/RIASEC elements) and `"motivation_preferred_minimum"` (`MOT-CHALLENGE`) in the dictionary, but `comparators_dispatch.py` had no dispatch branch for either — any real match touching a candidate/vacancy who'd answered those elements would have hit the final `raise ValueError(f"Unsupported comparator_key: {key}")` and crashed. Both are now implemented for real.

**Family 1 — Capability/Requirement** (`max(0, 100-25*shortfall)`, exceeding never penalized): `score_ordinal_requirement` (`src/match_engine.py`) upgraded in place from a 3-bucket discrete result to the real continuous formula — this single function covers the 6 TEAM capability elements and `TASK-YEARS` (all already wired to `ordinal_requirement`), no dictionary changes needed. New `score_capability_list_requirement` (`src/practical_comparators.py`) is the continuous-percent counterpart to the existing `score_tagged_list_overlap` for `CAP-SKILLS` — same tag-overlap/OR-across-required-tags matching semantics as before (unchanged), just a continuous shortfall percent instead of 3 discrete buckets for a matched tag.

**`EDU-HISTORY`'s Family 1, done as its own dedicated function** (`score_education_history`, `src/practical_comparators.py`) because it entangles three things the spec added across Phase 1 but never wired into scoring: the `consider` per-entry eligibility flag, "best entry wins" across eligible entries, and the new `education_field_requirement` (`required`/`preferred`/`open`) conditional field-mismatch logic that *replaces* the old blanket "field mismatch always caps" rule. `required` caps the entry's score to 0% on a field mismatch regardless of level; `open` ignores field entirely; `preferred` reduces (not zeroes) the level-based score via `EDUCATION_FIELD_MISMATCH_PREFERRED_FACTOR = 0.75` on mismatch. **Flagging this constant specifically**: the spec states `preferred` "reduces score but doesn't cap it" without a number — 0.75 is a documented, reasonable default in the same spirit as the spec's own framing of its Family 1/3 constants ("sound defaults... once real match data exists to validate against"), not a value taken directly from either source document. Worth confirming or tuning once real match data exists.

**Family 2 — Preference/Culture-fit** (`100-20*distance`, symmetric, floors at 20%): new `score_ordinal_distance` (`src/ordinal_comparators.py`), used by the 10 new single-value ENV-*/RIASEC elements. The pre-existing 9 ENV elements (and all 12 pre-existing MOT elements) deliberately stay on the old 4-value `ordinal_range`/`scale_id` format until Phase 3 migrates them — this was already the documented split from Phase 1; Phase 2 just makes the *new* format's formula real instead of a stub.

**Family 3 — Motivation** (preferred + minimum-acceptable, two different formulas gated on whether the vacancy clears the candidate's stated minimum): new `score_motivation_preferred_minimum` (`src/practical_comparators.py`), implementing both branches exactly per spec (`100-15*|actual-preferred|` floored at 40 when the minimum is cleared; `max(0, 40-20*shortfall)` when it isn't). Currently exercised only by `MOT-CHALLENGE` — the other 12 MOT elements stay on the old format until Phase 3.

**Family 4 — Categorical/Structured** (exact-or-close, not a numeric distance — correctly stayed on the existing discrete-Alignment architecture, no continuous score needed): `CAREER-PRIMARY-ROLE`/`CAREER-SECONDARY-ROLE` (`score_occupation_pick`, new in `comparators_dispatch.py`) now do a real ESCO occupation match — exact `esco_uri` match is `ALIGNED`; "close" is defined via ESCO's own ISCO-08-derived hierarchical `code` field (e.g. `"2166.3.1"`/`"2166.1"` share unit-group prefix `"2166"`) rather than inventing a new taxonomy — occupations sharing a unit group are `WEAK_ALIGNMENT`, upgraded to `ALIGNED` when the candidate flagged `open_to_adjacent`; no overlap at all is `MISALIGNED` unless the candidate flagged `still_exploring`/`open_to_adjacent`, which softens it to `WEAK_ALIGNMENT` with a clarification flag. Added `esco_occupation_unit_groups()` to `api/reference_search.py` (and a `code` field to `load_esco_occupations()`'s returned dicts — additive, existing callers only ever read `uri`/`label`). `CAREER-INDUSTRIES` (`score_industry_overlap`) reuses the existing `score_tagged_list_overlap` unleveled set-overlap primitive directly — NACE is section-level only in this system (21 sections, no sub-hierarchy), so "close" reduces to plain overlap, the same primitive `TASK-EXPERIENCE`'s occupation-domain matching already uses.

**Family 5 — Unscored context**: `CAREER-NARRATIVE`, `CAREER-DEVELOPMENT`, `TEAM-EVIDENCE` are now excluded from matching entirely at the source (`api/matching_service.py`'s `build_item_results` skips any element with `comparator_key == "unscored"` before activation resolution even runs) rather than generating an `UNKNOWN`/needs-clarification `ItemResult` for something that was never meant to be scored — this was already the stated Phase 2 plan left as a comment in Phase 1's stub.

**Verification**: 24 new unit tests (`tests/test_family_comparators.py`, exact-value assertions for every formula's boundary cases — shortfall 1-4, distance 0-4, both Family 3 branches, field-requirement `required`/`preferred`/`open`, `consider`-flag exclusion, best-entry/best-tag-wins) plus new integration tests in `api/tests/test_matching_service.py` (ESCO exact/close/no-match/`open_to_adjacent`/`still_exploring`, NACE overlap, Family 5 exclusion, continuous score flowing through `build_item_results` into `ItemResult.score` end to end). Full backend test suite: 221 passed. Additionally ran a real match (no persistence) against the live DB's actual dictionary (56 elements, every comparator_key currently in production) and 3 real talent_ids against a real vacancy_id — confirmed zero exceptions across every live comparator_key, and confirmed the 3 Family 5 elements are excluded (56 dictionary elements → 53 scored items) end to end against real data, not just in-memory test fixtures.

**Unrelated transient issue hit and fixed during this verification, not a Phase 2 regression**: a prior full-suite run was interrupted mid-test by a genuine Neon connectivity blip (DNS resolution failure against the pooler host), before `test_seed_fit_dictionary_safety.py`'s own `finally: DELETE` cleanup could run. That left one throwaway `TEST-SAFETY-*` row (plus its linked test talent/talent_element_value rows) stuck in the live `fit_element` table with `active=true`, which broke `load_dictionary()` — and therefore 5 unrelated tests calling it — since the row's `element_id` doesn't match its `category`'s required prefix. Diagnosed via traceback (not guessed), confirmed it was orphaned test residue rather than real data (test-owned UUID/email pattern), and deleted the 3 linked rows directly, mirroring the test's own cleanup logic exactly. Re-ran clean afterward.

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 3 (reset/migrate the *pre-existing* TEAM/MOT/ENV elements onto the new formats/formulas), Phase 4 (not_scored/unknown labeling + AI-extraction safeguard), Phase 5 (frontend), Phase 6 (vacancy-side wording), Phase 7 (live E2E with real accounts and a real match run).

---

## 2026-08-03 — v3 Fit Dictionary redesign, Phase 1 (schema): complete

**Permanent design record for this whole redesign**: `C:\Users\navid\Downloads\Launchino_Fit_Dictionary_Final_v3.docx` (primary spec — 5 scoring families, per-element changes) plus `Launchino_v3_Addendum.docx` (3 clarifications/reversals to it). Both read in full before any code was touched. This is a large, explicitly multi-phase task (7 phases total); this entry covers Phase 1 only. Phases 2-7 (real comparator formulas, data migration of the *pre-existing* ENV/MOT/TEAM elements, not_scored/unknown labeling, frontend, vacancy-side wording, live E2E) are not started and require the user's explicit go-ahead per phase.

**The 5 scoring families** (for later phases' reference): Family 1 Capability/Requirement (`max(0, 100−25×shortfall)`, no penalty for exceeding); Family 2 Preference/Culture-fit (`100−20×distance`, symmetric, floors at 20%); Family 3 Motivation (preferred+minimum vs. one vacancy actual value, two formulas depending on whether the actual clears the stated minimum); Family 4 Categorical/Structured (exact-or-close taxonomy match, ESCO/NACE); Family 5 Unscored (stored for human review, never a number).

**Two real discrepancies found between the spec and the live schema, resolved with the user before proceeding**: (1) `TEAM-VISIBILITY`/`TEAM-TONE` don't exist in the live dictionary — no-op, and `ENV-COMMUNICATION-DIRECTNESS` is simply a new element rather than a rename. (2) `TASK-EXPERIENCE` (Family 4, occupation match) vs. `TASK-YEARS` (Family 1, duration) — the doc's summary table and per-element table disagreed; user confirmed the per-element table's split is correct.

**Real-data safety finding, paused and resolved with the user before touching anything**: the spec assumed several elements slated for removal/restructuring had no real answered data. They didn't — `postdoc` had 2 real Task History-eligible entries, and the 6 CAREER free-text elements slated for removal/restructuring had 64-67 rows each. Rather than silently orphan or destroy this, flagged it and got an explicit 3-part mandate:
1. **Postdoc removal**: the 2 real postdoc `EDU-HISTORY` entries were migrated into Task History first, then `postdoc` was dropped from the education-level enum (`src/practical_comparators.py`, `EducationEntryEditor.jsx`, vacancy `RequiredEducationVacancy`).
2. **3 removed CAREER free-text elements** (`CAREER-PROBLEM-TYPES`, `CAREER-DESIRED-ACTIVITIES`, `CAREER-AVOIDED-ACTIVITIES`): deactivated (`active: false`) rather than deleted. `load_dictionary()`'s `where active = true` filter means they're excluded from matching/completion entirely, but their ~64 real rows per element stay in the DB, inert and unshown, not destroyed.
3. **`CAREER-PRIMARY-ROLE`/`CAREER-SECONDARY-ROLE`/`CAREER-INDUSTRIES`**: restructured to structured ESCO-occupation / NACE-industry schemas (`comparator_key: esco_occupation_pick` / `nace_industry_overlap`), but rather than orphaning the real free-text answers, reused the existing AI-mapping-with-confidence pattern (`api/mapping_service.py`, same shape as EDU's program→ISCED mapping) to migrate every *distinct* raw string once (caching per distinct value, not per row — most of the ~195 total rows were the literal placeholder `"example"`, so this was only 8 real AI calls, not ~195). **Real migration results**: PRIMARY-ROLE 2 auto-migrated / 64 flagged for candidate confirmation; SECONDARY-ROLE 0 auto-migrated / 64 flagged; INDUSTRIES 3 auto-migrated / 64 flagged. Flagged (low-confidence or unmatched) values keep their original `raw_text` and a `confidence` score; nothing was silently discarded — candidates will be prompted to confirm or re-pick next time they visit their profile (Phase 5 frontend work).

**New NACE reference dataset**: `data/reference/nace_industries.json` (21 NACE Rev. 2 sections, A-U), mirroring `isced_f_2013.json`'s structure; `load_nace_sections()`/`list_nace_sections()` added to `api/reference_search.py`; new `map_industry_to_nace()` in `api/mapping_service.py` and `prompts/P25_industry_nace_mapping.txt`, mirroring the existing ISCED program-mapping pattern exactly. `"industry_mapping"` added to `ai_client.MODEL_FOR_TASK` (haiku).

**13 new elements added** (all schema-only in Phase 1 — comparator formulas are Phase 2): `TEAM-EVIDENCE` (unscored, vacancy-activated), 6 `CAREER-INTEREST-*` (RIASEC, ordinal_distance, always-active), `MOT-CHALLENGE` (motivation_preferred_minimum, candidate-selected), 4 new `ENV-*` (ordinal_distance, always-active), `CAREER-NARRATIVE` (unscored, always-active). 6 existing `TEAM-*` capability elements got reworded `candidate_question`/simplified `candidate_value_schema` (vacancy side deliberately untouched — Phase 6). `CAREER-DEVELOPMENT`'s `comparator_key` changed to `unscored` with its `candidate_value_schema` left completely unchanged, preserving compatibility with its own real existing rows.

**Deliberate, temporary split** (not drift — will be resolved together in Phase 3): elements with zero real data (`MOT-CHALLENGE`, the 4 new `ENV-*`, the 6 RIASEC) were born directly in their final Family 2/3 schema. The *pre-existing* 9 `ENV-*`, 12 `MOT-*`, and `TEAM-COLLAB-INTENSITY` elements are deliberately left on the old `ordinal_range`+`scale_id` format for now, to be migrated together with real answered data in Phase 3, exactly as the user's phase breakdown specifies. `tests/test_survey_contracts.py` was updated to assert this split explicitly (`_NEW_ENV_MOT_ELEMENTS`), not to paper over it.

**Safety stubs for not-yet-implemented comparator keys**: `comparators_dispatch.py` returns `Alignment.UNKNOWN` with an explanatory reason for `esco_occupation_pick`, `nace_industry_overlap`, and `unscored`, instead of the pre-existing `raise ValueError` — so live production matching doesn't crash during the gap between Phase 1 (schema) and Phase 2 (real formulas).

Every non-additive schema change (`postdoc` removal, the 3 CAREER restructurings) went through the existing `_is_schema_change_additive_only` safety check and required an explicit `force_element_ids` override, confirmed intentional each time. Full backend test suite (190 tests) passes — 4 failures surfaced by the real schema changes were fixed to match the new correct state (not silenced): `data/candidate_survey.json`/`vacancy_workshop.json` updated for `MOT-CHALLENGE` (documentation-only artifacts, confirmed via grep not used by live runtime code); `test_environment_and_motivation_use_five_point_scales` rewritten to assert the deliberate old/new ENV/MOT split; `test_premium_ready_flips_as_real_coverage_crosses_the_real_threshold`'s fixtures updated for the new always-active elements and new CAREER schema shapes (`values_stored` 28 → 36); `test_model_for_task_mapping_is_correct_per_task` extended for `industry_mapping`.

Not yet done, by design — reported back to the user for explicit go-ahead before starting: Phase 2 (5 comparator families' real formulas + unit tests), Phase 3 (reset/migrate existing TEAM/MOT/ENV data), Phase 4 (not_scored/unknown labeling + AI-extraction safeguard), Phase 5 (frontend), Phase 6 (vacancy-side wording), Phase 7 (live E2E with real accounts).

---

## 2026-07-31 — Logo icon's navy dot on the nav bar: outline attempt swapped for a lighter solid fill (wasn't effective enough)

Follow-up to the entry right below: the `stroke="#4A5080"` outline fix wasn't visually strong enough in practice, even though it was technically non-zero contrast.

**Switched to a solid, lighter fill instead of an outline.** `frontend/src/assets/logo-icon-on-navy.svg`'s navy dot `<circle>` now has `fill="#5B62A0"` (no `stroke` at all) instead of `fill="#151A45" stroke="#4A5080"`. Computed WCAG contrast ratios confirm why the outline undersold it and the new fill doesn't: `#151A45` (original) vs `#151A45` (nav bg) = 1.00 (invisible, by definition); the `#4A5080` outline attempt = 2.17; the new `#5B62A0` fill = **2.92** -- actually higher contrast against the same nav bar than the purple dot's own `#7F2FA3` (2.24), so the navy dot now reads at least as clearly as the icon's other two dots, not just barely above invisible. Purple dot, gold dot, and the turquoise trail are untouched -- only this one `<circle>`'s fill changed, and only in this navy-background variant.

Verified live in a browser (same method as the entry below, repeated after this change): a real authenticated candidate's `TopNav` icon source confirms `fill="#5B62A0"`, no stroke; the login page's hero mark source still reads `fill="#151A45"`, completely unchanged -- the two variants remain genuinely decoupled. No frontend test suite exists to cover this. Full backend test suite passes (unaffected, frontend-only asset change).

---

## 2026-07-31 — Fixed the logo icon's navy dot disappearing on the navy nav bar

The icon mark's navy dot (`#151A45`) is the same color as `nav.top-nav`'s background, so it was invisible there -- worked fine everywhere else (login page hero, favicon) since those all sit on light/different-colored backgrounds.

New `frontend/src/assets/logo-icon-on-navy.svg`, identical to `logo-icon.svg` except the navy dot's `<circle>` gets `stroke="#4A5080" stroke-width="1.5"` (a lighter slate-navy, enough contrast against the navy fill without standing out on light backgrounds either). `App.jsx`'s `TopNav` now imports this variant instead of the plain icon; every other usage (`LoginPage.jsx`'s hero mark, `frontend/public/favicon.svg`) is untouched -- the favicon in particular is a wholly separate, unrelated asset (a different abstract mark, not this dot/circle icon), never affected by this change to begin with.

No frontend test suite exists in this repo to cover a UI component like this (no test files, no `test` script in `frontend/package.json`) -- verified live in a browser instead: a real authenticated candidate's `TopNav` icon now renders the navy dot with the `#4A5080` outline against the `rgb(21,26,69)` (`#151A45`) nav bar background, clearly visible; the login page's hero mark still renders the original, un-outlined SVG, confirming the two are genuinely decoupled, not the same asset conditionally styled. Full backend test suite passes (unaffected, as expected for a frontend-only asset change). **Superseded by the entry above -- the outline wasn't visually strong enough, replaced with a solid fill.**

---

## 2026-07-31 — Real bug fix: `contact_preference`'s DB default made a fresh account's Account Settings look "Complete" before any real choice was made

Reported directly: a genuinely fresh account showed Account Settings as "Complete," violating the same answered-vs-never-touched principle this system already enforces everywhere else (Fit Dictionary elements' `value_status`, `dashboard_intro_seen`, etc.).

**Diagnosis (checked before touching anything, per the request):**
1. `talent.contact_preference` was `text not null default 'email'` (`src/database_schema.sql`, from `migrations/006_v2_2_0_to_v2_3_0.sql`) -- registration's `INSERT` never sets it explicitly, so every fresh row got a real, stored `'email'` the instant it was created. Never genuinely NULL.
2. `AccountSettingsPage.jsx` initialized `useState('email')` and fell back with `candidate.contact_preference || 'email'` on load -- the shared `Select` component's own "-- choose --" placeholder (already used correctly elsewhere, e.g. Education level) was never reachable, because a real value was always present by render time.
3. `compute_candidate_completion`'s `basic_info_complete` (fixed two entries ago in this file to be conditional on `contact_preference == 'phone'`) only ever checked "did they choose phone without providing one" -- not "did they ever make a genuine choice at all." Since the column was never actually NULL, that check was trivially true immediately, reproducing exactly this bug.

**Also found during diagnosis, load-bearing for the fix**: `TalentOut.contact_preference` and `Talent.contact_preference` (the Pydantic response models, `api/models_api.py`/`src/schemas.py`) were *also* non-optional with a `= ContactPreference.EMAIL` default -- fixing only the DB column without these would have either crashed every fresh candidate's API response (pydantic rejects an explicit `None` against a non-Optional field) or kept fabricating `"email"` in the JSON even with a genuinely NULL DB row.

**Fix**: `contact_preference` now has no default and is genuinely nullable end to end.
- `src/database_schema.sql` (fresh installs) and new `migrations/010_v2_6_0_to_v2_7_0.sql` (applied live to the shared DB) drop both the `NOT NULL` and the `DEFAULT 'email'`. Existing rows are left untouched -- there's no way to tell a genuine past choice of 'email' from one that was only ever the default, so this only changes behavior for accounts created from now on (flagged here as a known, permanent gap in the existing ~350+ rows, not silently resolved either way).
- `TalentOut.contact_preference`/`Talent.contact_preference` -> `Optional[ContactPreference] = None`.
- Registration's own `TalentOut(...)` construction (`api/routers/candidates.py`) now explicitly passes `contact_preference=None` instead of relying on the model's own (now-removed) default.
- `compute_candidate_completion`'s `basic_info_complete` now also requires `contact_preference is not None`, not just "isn't 'phone'."
- `AccountSettingsPage.jsx`: initial state and load-fallback both use `''` instead of `'email'`, so the Select's existing "-- choose --" placeholder genuinely shows until a real choice is made. Added `required` support to the shared `Select` component (`formFields.jsx`, mirroring `TextField`'s existing pattern) and used it here, so an empty submit is blocked client-side, matching the phone field's existing conditional-required pattern -- the backend already independently rejects an empty value too (`BasicInfoUpdate.contact_preference: Optional[ContactPreference]` fails Pydantic validation before reaching any business logic).

Updated three existing tests whose assertions relied on the old default (`test_completion_starts_at_zero_and_tracks_real_answers`, `test_basic_info_complete_is_conditional_on_contact_preference`, `test_basic_info_partial_update_and_defaults`) and extended the conditional-completion test with an explicit "make a real choice -> now complete" step. Full backend test suite (190, same count -- no new test functions, just corrected/extended assertions) passes.

Verified live in a local browser against a genuinely fresh candidate: dashboard showed Account Settings "Not started" and "Continue: Account Settings" immediately after registration (not "Complete"); the Account Settings form's contact-preference dropdown showed "-- choose --" selected, not "Email"; selecting "Email" and saving flipped Account Settings to "Complete" and the CTA correctly advanced to "Continue: Education." Also confirmed directly against the database that a mid-reload stale API response during this same verification (showing `"email"` in one throwaway response) did not reflect a real DB value -- the row itself was already correctly `NULL`.

---

## 2026-07-31 — Real bug fix: CV-imported Education wasn't actually saved; Account Settings restored to the front of the Continue queue (and a real underlying bug fixed to make that safe); Task History reordered to directly follow Education

Reported directly after the previous entry's changes went live: CV extraction looked confirmed but Education wasn't saved, and the "Continue" CTA no longer started at Account Settings. Both were real regressions from this session's own recent changes, not user error.

**Real bug: `CvImportPanel`'s "Confirm and save" saved phone and Task History immediately but silently left Education unsaved.** The previous entry's design deliberately deferred Education to the Education page's own separate "Confirm and submit" button -- reasonable in the abstract, but the single "Confirm and save" button gave no indication that only *some* of what it reviewed was actually being persisted. A candidate who pasted a CV, reviewed the result, hit "Confirm and save", and moved on had every reason to believe it was saved -- it wasn't, for Education specifically. Fixed by making `EducationPage.jsx` persist Education immediately too: extracted `saveEducation(entriesToSave)` out of the page's existing submit handler, and its `onEducationExtracted` callback (passed to `CvImportPanel`) now merges the extracted entries into local state *and* awaits an immediate save, matching how Task History/phone already behaved. `CvImportPanel.jsx` now awaits that callback so a save failure surfaces through its own existing error UI rather than being silently swallowed. Verified against a real local candidate: `GET .../survey-values` showed `EDU-HISTORY` correctly persisted (and the EDU category flipped to "complete") immediately after "Confirm and save", without ever touching the page's own "Confirm and submit" button.

**Account Settings restored to the front of the "Continue" queue** (`CandidateDashboardPage.jsx`'s `nextIncomplete`) -- this exact branch was deliberately *removed* two entries ago in this file to fix a real stuck-CTA bug, but removing it was routing around the actual root cause rather than fixing it. Root cause, found this time: `compute_candidate_completion`'s `basic_info_complete` was `bool(phone)` unconditionally, even though the "conditional phone requirement" work (see the 2026-07-30 entry below) had already made phone genuinely optional except when `contact_preference == 'phone'` -- the write-side validation was fixed at the time, but this read-side completion flag never was. That mismatch, not the CTA's ordering, was the real bug: a candidate with the default `contact_preference` ('email') and no phone was being shown "Not started" on Account Settings and would have gotten stuck on that CTA forever if it were ever checked first. Fixed at the source: `basic_info_complete` now mirrors the write-side rule exactly (`contact_preference != 'phone' or phone`), so Account Settings can safely lead the queue again. New test `test_basic_info_complete_is_conditional_on_contact_preference` (`api/tests/test_candidate_completion.py`) covers both the common case (default 'email', no phone, correctly complete) and the genuine incomplete case -- the latter is unreachable through the API once phone has ever been set (a `None` update is dropped as "no change", per `set_candidate_basic_info`'s own docstring, never a clear), so that half is simulated with a direct DB write, confirming the read-side conditional still correctly flags data that predates -- or otherwise bypasses -- that write-side guard. Existing test `test_completion_starts_at_zero_and_tracks_real_answers` updated: a fresh candidate's `basic_info.complete` is now `True` from registration (nothing's actually missing yet), not the previous `False`.

**"What you've done" (TASK) moved to directly follow Education** in `CANDIDATE_DASHBOARD_CATEGORY_ORDER` (`api/candidate_service.py`) -- was last of the 8; now second, right after EDU. This is the single source of truth for both the dashboard's card grid and the "Continue" walk order, so both updated together with a one-line change (confirmed via grep this constant has exactly one definition and one consumer).

Full backend test suite (190 -- 189 existing + 1 new) passes. Verified live in a local browser end to end: dashboard card grid reads Account Settings -> Education -> What you've done -> Practical fit -> ...; a fresh candidate's Account Settings correctly shows "Complete" immediately (no phone needed by default) and the CTA correctly advances past it to "Continue: Education"; a real CV-extraction-and-confirm on the Education page now persists Education immediately, confirmed via a direct API check before ever touching the page's own submit button.

---

## 2026-07-31 — Dashboard explainer restyled and moved to the top, login logo made hero-sized, Postdoc education level added, CV extraction relocated to the Education page, and a fresh "What you've done" live-site re-check

Five items in one pass.

**1. Dashboard explainer moved above the profile-completion header, restyled to look interactive.** `DashboardIntro.jsx` now renders first in `CandidateDashboardPage.jsx`, before the "Your profile"/percent-complete header (previously below the Continue button). Restyled the toggle row itself: a sparkles icon, a bold title, a subtle `--ll-neutral-100` background with a `--ll-neutral-200` border on the whole card, and a single chevron that rotates 180° via a CSS transition on click (previously it swapped between two different chevron icon components with no animation) -- collapsed-by-default/auto-expand-once-on-first-visit behavior is unchanged. Verified locally: computed styles confirm the background color, bold title, and a `rotate(180deg)` transform matrix on the chevron while expanded.

**2. Login page logo made hero-sized.** `LoginPage.css`: icon 72px -> 120px, wordmark 24px -> 44px, and `.ll-hero-mark` centered (`justify-content: center`) rather than left-aligned inline with the rest of the hero copy -- reads as a proper brand mark now, not the same small sizing as `TopNav`'s 24px nav logo (`App.css`, untouched, confirmed a separate class so this couldn't cross-affect the nav). Verified locally via computed styles.

**3. Added "Postdoc" as an education level**, ranked above PhD. Touched every place the level enum actually lives: `EducationEntryEditor.jsx`'s `LEVELS` array (candidate-side), `valueEditors/index.jsx`'s `RequiredEducationVacancy` `requirementLevels` (vacancy-side, so an employer can require one too), `practical_comparators.py`'s `EDUCATION_LEVEL` ordinal dict (`"postdoc": 6`, actually enforced in comparisons -- the real ranking, not just UI), and `data/fit_dictionary_starter.json`'s two documentary `level` enum strings on EDU-HISTORY (informal, human-readable only -- nothing parses them). That last change was a real, live test of the schema-change safety check documented in the entry right below this one: since it's a leaf-string change on an element with real answered `talent_element_value` rows, `seed_fit_dictionary()` correctly refused to auto-apply it on the next backend reload (`seed_fit_dictionary WARNING: skipped 'EDU-HISTORY'`) even though it's genuinely harmless -- pushed it through deliberately via `force_element_ids={'EDU-HISTORY'}`, confirmed via direct query that the stored schema now reads `...phd|postdoc|other` and `...phd|postdoc`. Verified locally: the Level dropdown lists `postdoc` between `phd` and `other`, both on the candidate Education page and the company's required-education vacancy editor.

**4. CV extraction relocated from a dashboard gate to an opt-in panel on the Education page.** Removed `QuickStartCvCard.jsx` (dashboard-level, shown before any category) entirely, along with `CandidateDashboardPage.jsx`'s `showQuickStart`/`eduStatus`/`taskStatus` gating logic -- a CV paste is something a candidate does *while* working on Education, not a gate before reaching any category. New `CvImportPanel.jsx`, embedded in `EducationPage.jsx` above the entries editor, collapsed by default behind a "Have a CV? Paste it here to speed this up" toggle. Extraction still covers Education + "What you've done" together (`CV_EXTRACTION_CATEGORIES = {EDU, TASK}`, unchanged) since one CV is the real source for both, but the two categories are now handled asymmetrically on confirm: phone and TASK-EXPERIENCE are saved immediately by the panel (Education page doesn't otherwise own either), while the reviewed EDU-HISTORY entries are handed back to `EducationPage.jsx` via `onEducationExtracted` and merged into its own local `entries` state -- they aren't persisted until the candidate hits that page's own pre-existing "Confirm and submit" button, same as any manually-typed entry, not a second parallel save path. Also dropped `unmapped_terms`/`review_flags` from the review screen entirely -- both were leftover extraction output with no home in the real profile, so showing them was noise once nothing else in the review already-trimmed screen exists to explain. Verified locally with a real CV-extraction API call: review screen showed only Phone/Education/"What you've done" (confirmed via DOM check that neither "unmapped" nor "review flag" text appears anywhere), confirming and saving immediately persisted the extracted TASK-EXPERIENCE job and phone (checked via `GET .../survey-values` and `.../completion` before touching the Education page's own submit button), while EDU-HISTORY stayed unsaved (`None`) until the page's own "Confirm and submit" was clicked, after which the dashboard correctly showed Education/What you've done/Account Settings all complete.

**5. Fresh re-check: is "What you've done" actually showing on the live dashboard?** Reported as not appearing despite an earlier session claiming it was verified live. Checked fresh rather than trusting the prior claim: confirmed `540fcbc` (the relabel commit) is on `master` and pushed: `git log origin/master` matches local. Fetched the live deployed bundle (`index-xRgGZZyb.js`) -- contains "What you've done", no "Task History" anywhere. Called the live `GET .../completion` API directly against a fresh throwaway candidate on `api.launchino.com` -- returned `"What you've done"` for the TASK category. Then went further than just checking the API/bundle text: logged into the actual live dashboard in a real browser session (fresh candidate, no prior cache) and read the rendered page -- it genuinely shows "What you've done", not "Task History", right now. Checked response headers too: both `index.html` and the hashed JS bundle serve `Cache-Control: public, max-age=0, must-revalidate` from Vercel, so a stale copy can't persist server-side. The most likely explanation for the original report is a browser tab that was already open (with the old JS in memory) before the relabel deployed, and never reloaded -- server-side caching isn't a plausible culprit here, and the current live state is correct. No code change was needed for this item.

Full backend test suite passes (see next entry's cleanup commit for the exact count -- no test changes were needed for items 1/2/4/5, and item 3's only test-suite-relevant change, `EDUCATION_LEVEL`, has no dedicated test asserting the full key set, only that leveled comparisons using it behave correctly, which they still do).

---

## 2026-07-31 — `bootstrap()`'s automatic Fit Dictionary reseed now has a safety check before overwriting elements with real answered data

Triggered by a "not urgent" question: does `seed_fit_dictionary()` (run on every app startup, including every production deploy, via `bootstrap()`) have any check before applying a schema change, or does it just silently upsert whatever's in `data/fit_dictionary_starter.json` every time? Answer was: no check at all. Since we're about to lean on this mechanism again for a bigger schema change, built the safety net first.

**New: `_is_schema_change_additive_only(old_schema, new_schema)`** (`api/database.py`) -- a conservative recursive structural diff over the informal `candidate_value_schema`/`vacancy_value_schema` shapes (dicts, single-template-object arrays like `"jobs": [{...}]`, and leaf type-description strings like `"string|null"`). Returns `True` only if every key in the old schema still exists in the new one with an unchanged shape/type -- new optional keys are fine, but a removed key, a renamed key (structurally indistinguishable from remove+add), or a changed leaf type are all "incompatible." Deliberately errs toward flagging more things as incompatible rather than fewer -- this only has to correctly say yes to the genuinely safe case (add a field), not adjudicate every case that might turn out fine in practice.

**`seed_fit_dictionary()` rewritten**: before upserting an element that already exists, it now compares incoming vs. stored `candidate_value_schema`/`vacancy_value_schema` via the function above. An incompatible change is only actually blocked if real rows already exist for that element in `talent_element_value`/`vacancy_element_value` (new `_element_has_existing_candidate_data`/`_element_has_existing_vacancy_data` helpers) -- an incompatible change to an element nobody has answered yet still applies automatically, since there's nothing to protect. When blocked: the element's row is left completely untouched, a `print()` warning is logged (this codebase has no logging framework, so this matches its existing minimal-tooling convention), and it's reported in a new `skipped` list in the return value (changed from a bare `int` to `{"seeded_count": int, "skipped": [{"element_id", "field"}]}` -- confirmed via grep nothing depended on the old return type). Added an `elements: Optional[list] = None` injection parameter (same DI pattern as `run_poll_cycle`'s `client` param elsewhere in this codebase) so tests can pass a synthetic "incoming" schema without needing two different real states of the fixed starter JSON file.

**Explicit override: `FIT_DICTIONARY_FORCE_SCHEMA_CHANGES`** env var (comma-separated `element_id`s), read once in `bootstrap()` into a `frozenset` and passed through to `seed_fit_dictionary(force_element_ids=...)`. An element_id in this set skips the safety check entirely for that startup -- the intentional escape hatch for "I've already migrated the existing rows to match, go ahead."

**Real manual demonstration against the actual live `TASK-EXPERIENCE` element** (this project has one shared Neon DB, no separate staging tier, so this was necessarily against production): inserted a real throwaway `talent`/`talent_element_value` row, attempted a `job_title` -> `role_name` rename -- correctly blocked, DB schema unchanged. Forced it via `force_element_ids` -- correctly applied. Then tried to "restore" the real schema by calling with no args (reads the real JSON, which still says `job_title`) -- this was *also* blocked, because from the now-renamed DB's perspective, reverting looked like just another incompatible change. Not a bug: the check has no notion of which side is "canonical," only "does this look like a safe change" -- correct, symmetric behavior. Force-applied the real schema back and confirmed via direct query that `TASK-EXPERIENCE` is back to its correct live shape (`job_title`, not `role_name`). Cleaned up the throwaway talent row.

**10 new tests** (`api/tests/test_seed_fit_dictionary_safety.py`): 6 pure unit tests against `_is_schema_change_additive_only` (new key, removed key, renamed key, type change, nested-array new key, empty-list placeholder treated as compatible), plus 4 real-DB tests using synthetic throwaway `element_id`s (`TEST-SAFETY-<uuid>`, never a real element like `TASK-EXPERIENCE`, specifically so repeated CI runs can never corrupt real Fit Dictionary metadata the way the manual demonstration above required a force-restore) covering: blocked when real data exists, force-flag overrides the block, no block when no real data exists yet, and a purely additive change (e.g. today's `employer` field) still applies automatically with no force flag needed, exactly as before this check existed.

**Follow-up, same day: made the warning actually loud in production, not just technically present.** Both `print()` calls (the per-element warning inside `seed_fit_dictionary()`, and the startup summary in `bootstrap()`) were logging correctly, but `bootstrap()` runs once inside the long-lived FastAPI/uvicorn server process (`api/main.py`'s `lifespan` handler), not a short-lived script -- when stdout is piped, as it is under Render, Python block-buffers by default, so a startup print in a process that then runs indefinitely could sit unflushed far longer than acceptable instead of showing up immediately in Render's log stream. (This codebase's other `print()` usage, in `job_discovery_scheduler.py`, is all in short-lived CLI runs where the process exit flushes the buffer anyway -- bootstrap's case is genuinely different, not covered by an existing convention.) Added `flush=True` to both calls so a skip is guaranteed visible in Render's deploy/runtime logs the moment it happens.

Full backend test suite (189 -- 179 existing + 10 new) passes.

---

## 2026-07-31 — CV extraction scope moved from Practical fit to "What you've done"/Task History; that category relabeled and made non-traditional-experience-friendly

**CV extraction scope: `CV_EXTRACTION_CATEGORIES` changed from `{PRACT, EDU}` to `{EDU, TASK}`.** Practical fit facts (visa/sponsorship/location/work-mode) are exactly the kind of thing a candidate should state themselves, not have inferred from CV text; TASK-EXPERIENCE's job/role entries are exactly what a CV *is* a record of, and its ESCO occupation mapping already works the same best-effort, non-blocking way EDU's institution/program mapping does regardless of entry origin -- there's no second, diverging path, just one real mapping endpoint fed by two entry points into the same raw text (`api/extraction_service.py`'s updated comment has the full reasoning). Updated `prompts/P01_cv_extraction.txt`'s SCOPE section and `CV_VALUE_SCHEMA_RULE`'s worked examples (previously all PRACT-based, now EDU/TASK-based, since PRACT no longer reaches the model at all). **Confirmed, not assumed, that Account Settings (phone) stays fully unaffected**: `CandidateExtractionResult.basic_info` is a structurally separate top-level field from `extracted_elements`/category scoping (`src/candidate_extraction.py`), so it was never affected by which categories are in `CV_EXTRACTION_CATEGORIES` in the first place. Verified with a real API call: a CV explicitly stating visa/sponsorship/work-mode/location facts alongside a job and a personal project produced `extracted_elements` containing only EDU-HISTORY/TASK-EXPERIENCE -- the practical-fit facts were correctly recognized by the model but landed in `unmapped_terms` (nowhere to put them, exactly as intended) rather than as PRACT-* elements, and `basic_info` contained only `phone`.

**Task History relabeled to "What you've done"** (`api/candidate_service.py`'s `CATEGORY_LABELS`, `data/fit_dictionary_starter.json`'s TASK-EXPERIENCE `label`/`definition`/`candidate_question`/`evidence_rule`, `TaskHistoryPage.jsx`'s `<h1>`/description copy) to be inclusive of internships, projects, and other non-traditional experience, not just formal jobs. The entry field itself relabeled from "Job title" to "Role or project name". Reseeded the live `fit_element` table via `seed_fit_dictionary()` (also runs automatically on every app startup through `bootstrap()`, so this propagates to production on deploy without a separate manual step).

**New: employer/organization field**, free text, purely informational -- never matched or mapped to anything, same pattern as Education's institution name. Added to `TASK-EXPERIENCE`'s `candidate_value_schema` (`jobs[].employer`). Verified live: a project entry with employer left blank saved and displayed correctly, distinct from a formal job entry with a real employer name.

**Per-entry duration added, alongside the existing aggregate total.** A single entry's own start/end date diff needs no overlap-merge (`src/task_years.py`'s server-side algorithm only matters once you're combining *multiple* ranges), so this is computed client-side in the new shared `TaskEntryEditor.jsx` without risking a second, drifting copy of that real algorithm. Verified live: two entries (2019-2022 and a 5-month 2023 project) each showed their own correct duration ("3 yrs" / "5 mos") alongside the still-server-computed aggregate total ("3").

**Extracted two shared components** rather than duplicating entry-editing UI a third time: `TaskEntryEditor.jsx` (job/role/project entries, mirroring `EducationEntryEditor.jsx`'s existing extraction pattern from earlier this session) is now used by both `TaskHistoryPage.jsx` and the dashboard's `QuickStartCvCard.jsx`, which also needed its own PRACT-review section replaced with a TASK-review section (and its visibility condition switched from checking Practical fit's status to checking TASK's) to match the new extraction scope.

**Also moved "What Launchino does for you" to below the "Continue" button** on the candidate dashboard, per request -- was directly below the header.

Full backend test suite (179, unchanged count -- existing extraction-scoping tests updated in place, not added to) passes. Verified live end to end: dashboard card and quick-start copy both read "What you've done"; a real CV-extraction call correctly scoped to EDU+TASK only; a real Task History submission with a formal job and a blank-employer project, both showing correct per-entry and total durations; the explainer section now renders after the Continue button.

---

## 2026-07-31 — Re-diagnosis found items 1/2 already fixed and live; added the dashboard explainer section and login-page logo consistency

Four items requested; the first two turned out to already be fixed and deployed.

**Item 1/2 re-diagnosis: the CV-extraction and Account Settings/CTA fixes from earlier today were reported as broken on the live site -- checked fresh rather than assumed, found they're not.** Confirmed via `git log` that both fixes (`6aa7174`, `ffbbfbb`) are on `master` and pushed. Fetched the actual deployed bundle (`https://launchino.com/assets/index-fK2cWM86.js`) and confirmed it contains "Account Settings"/"Danger zone"/"Quick start" and no "Basic Info"/old CV-step text. Then, rather than trust bundle-text presence alone, registered a genuinely fresh candidate directly against the live production API (`api.launchino.com`) and walked it in a real browser: the quick-start card appears at the very top of the dashboard (the only place CV extraction is offered), Education/Practical fit/"How you work" all go straight to their manual questions with no CV step of their own, and -- the strongest confirmation, since this exact candidate had never touched Account Settings -- the CTA read **"Continue: Education"**, not "Continue: Account Settings"; under the old bug this exact state (phone never set) would have shown the stuck CTA forever. Both fixes are live and correct. No code changed for these two items. The discrepancy the user observed was most likely a stale/cached view or a test against an account with pre-existing category progress (which correctly hides the now-relocated quick-start card) rather than a real gap -- flagged, not silently dismissed, since "the live site doesn't match" deserved a real check, not an assumption either way.

**New: "What Launchino does for you" dashboard explainer.** Collapsible section (`frontend/src/components/DashboardIntro.jsx`), placed below the header and above the category cards/quick-start card, with the exact copy provided. Needed a real persisted per-candidate flag, not a client-only or completion-percentage-based heuristic: `overall_percent_complete === 0` stays true on every revisit until real progress exists, so it can't distinguish "first visit ever" from "tenth visit, still nothing saved." Added `talent.dashboard_intro_seen boolean not null default false` (`migrations/009_v2_5_0_to_v2_6_0.sql`), included in `GET /candidates/{id}/completion`'s response, and a new idempotent `POST /candidates/{id}/dashboard-intro-seen` the frontend calls the instant it auto-expands. Verified live: a genuinely fresh candidate sees it auto-expanded with the full 4-paragraph copy; reloading the same dashboard shows it collapsed by default; the toggle still opens/closes it manually any time afterward.

**Login page logo consistency.** `LoginPage.jsx`'s hero previously rendered a script wordmark for the candidate role tab and a sans wordmark for company/admin (`HERO_COPY[role].word`) -- now always renders the same icon + sans wordmark (`ll-wordmark-sans`) as the dashboard/nav's `TopNav`, on every role tab, deliberately overriding that split for this one page per explicit instruction. Removed the now-fully-unused `word` field from all three `HERO_COPY` entries rather than leave dead config sitting next to logic that no longer reads it.

Full backend test suite (179 -- 178 existing + 1 new `dashboard_intro_seen` test) passes.

---

## 2026-07-31 — Account Settings rename, account deletion UI, and a second real regression fixed: the "Continue" CTA was permanently stuck

Three related changes to what was "Basic Info."

**Renamed "Basic Info" -> "Account Settings"** throughout the candidate-facing UI: dashboard card label (`api/candidate_service.py`'s `compute_candidate_completion` -- the label string lives server-side), page `<h1>`, and the page/component/route itself (`frontend/src/pages/BasicInfoPage.jsx` -> `AccountSettingsPage.jsx`, route moved from `/candidate/survey/basic-info` to `/candidate/account-settings` -- `categorySlugs.js`'s `BASIC_INFO_PATH` -> `ACCOUNT_SETTINGS_PATH`, out of the `/survey/` URL namespace since it's no longer part of that sequence at all, see below).

**Account deletion added, reusing the existing endpoint verbatim.** `DELETE /candidates/{talent_id}` (built during the earlier security/GDPR work) already anonymizes correctly -- no backend changes made or needed. New "Danger zone" section on the Account Settings page: a "Delete my account" button reveals a second stage requiring the candidate to type the literal word `DELETE` before the real "Permanently delete my account" button enables -- not a single click, matching the irreversibility of the action. On success, calls the same `logout()` the existing "Log out" link already uses, letting `RequireRole`'s own redirect-to-`/login` take over -- no second redirect mechanism invented. No test existed for this endpoint before despite it being a real GDPR erasure mechanism; added one (`api/tests/test_candidate_delete_endpoint.py`) confirming, for real: tombstoned name/email, cleared password (can't log back in), `talent_element_value` rows hard-deleted, and that a second delete on an already-anonymized row is still a clean 200 (re-deletable, not a special-cased error).

**A second real regression found and fixed: the "Continue" CTA could get stuck on Account Settings forever.** Root-caused, not assumed: `CandidateDashboardPage.jsx`'s `nextIncomplete` checked `!completion.basic_info.complete` *first*, before ever looking at `completion.categories` -- and `basic_info.complete` depends solely on `phone` being set (per the 2026-07-30 Basic Info trim entry below). Since phone is optional for every `contact_preference` except `'phone'` itself, any candidate who legitimately never sets a phone number would see "Continue: Account Settings" forever, even after finishing all 8 real categories -- it could never advance, because the ternary always re-resolved to Account Settings first. This is a real regression, not the original design: the Phase 4 entry below explicitly says Basic Info was "surfaced as its own dashboard concept" specifically so it could "never be accidentally swept into `overall_percent_complete`'s denominator" -- the completion *percentage* guard existed, but nothing equivalent guarded the separate CTA computation, and it silently grew this same class of bug. Fixed by dropping the Account-Settings branch from `nextIncomplete` entirely -- it now only ever considers `completion.categories`. Account Settings remains reachable at any time via its own standalone dashboard card (unchanged), just never part of the sequential queue.

No backend changes were needed for the CTA fix (purely a frontend computation) or the deletion feature (endpoint reused as-is); only the completion label string changed server-side for the rename.

Full backend test suite (178 -- 177 existing + 1 new delete-endpoint test) passes. Verified live in a browser: dashboard card and page both read "Account Settings"; a candidate who completed Practical fit but never set a phone sees "Continue: Education" (not stuck); Danger Zone's confirm button stays disabled until "DELETE" is typed, then a real deletion anonymized the account exactly as the endpoint documents and logged out to the login page.

---

## 2026-07-31 — Real regression found and fixed: CV extraction had drifted onto every category page instead of one dashboard step

Prompted by the user asking me to re-verify Phase 3/4's CV-extraction design fresh rather than trust the old report. Found a real bug, not assumed from memory:

**What was actually wrong.** `api/extraction_service.py`'s `CV_EXTRACTION_CATEGORIES = {PRACT, EDU}` was still correct and untouched -- the backend never drifted. But the frontend did: `CategorySurveyPage.jsx` (the shared component behind PRACT/TEAM/CAREER/MOT/ENV's 5 routes) offered "Share your CV, or start from scratch" identically on **all 5** of those pages, not just PRACT. Confirmed live: pasted a CV on the "How you work" (TEAM) page, and the AI correctly recognized team-preference content and flagged it in "Notes from extraction" as something it couldn't record -- but the actual question below still showed unfilled defaults. A real, wasted round trip. Meanwhile Education (its own dedicated page, `EducationPage.jsx`) had no CV-extraction entry point at all, despite being backend-eligible.

**When and how this happened**, traced via `git log`: the original pre-Phase-4 design (`CandidateSurveyPage.jsx`, single page) had exactly one CV step, shown once, before every category rendered together on that one page. Commit `869680d` ("Split survey into 5 per-category pages") carried that same step verbatim into the new shared `CategorySurveyPage.jsx` to fix a different, real bug ("CV-extraction had become unreachable through the UI") -- but the fix reintroduced the step on all 5 pages equally instead of scoping it to the one category that could actually use it. A correct fix for one bug quietly created another.

**The fix**, matching the architecture the dashboard-hub redesign actually needs (asked the user where the one-time step should live now that there's no single linear page anymore; chose a new dashboard-level step over patching around the old per-page one):
- Removed the CV-paste step entirely from `CategorySurveyPage.jsx` -- all 5 of its routes (PRACT/TEAM/CAREER/MOT/ENV) now go straight to manual entry, same as TEAM/CAREER/MOT/ENV already correctly did.
- New `QuickStartCvCard.jsx`, shown once at the top of `CandidateDashboardPage.jsx` -- only while Basic Info, Education, and Practical fit are *all* still not-started (the real "very start of the journey" condition in a hub architecture, since any one of them having data means the candidate already engaged some other way). Paste once -> review phone + every Practical-fit question + Education entries together on one screen -> "Confirm and save" writes phone (`PATCH .../basic-info`), Practical fit and Education-History (both via one `POST .../survey` call). Card disappears once saved, matching the "one-time" requirement structurally, not just by convention.
- Extracted the entry-editing UI (level/institution/programme/dates/status, ISCED-F mapping) out of `EducationPage.jsx` into a shared `frontend/src/components/EducationEntryEditor.jsx`, reused by both the standalone Education page and the new quick-start review screen, rather than duplicating it.

No backend changes were needed -- `CV_EXTRACTION_CATEGORIES` and `POST /candidates/{id}/extract-cv` were already correctly scoped; this was purely a frontend reachability/UX regression.

Full backend test suite (177, unchanged) still passes. Verified live end to end: fresh candidate sees the quick-start card, pastes a CV, gets phone/education/practical-fit all correctly pre-filled for review, confirms, and the card disappears while Basic Info/Education/Practical fit all show Complete on the dashboard; separately confirmed "How you work" now goes straight to its question with no CV offer at all.

---

## 2026-07-30 — Basic Info trim: show name/email read-only, drop `linkedin_url` entirely, remove the dead-end `in_app_only` contact preference

Prompted by a real question raised while reviewing the Basic Info page: does choosing "contact me in-app only" actually do anything? Checked -- there is no messaging/inbox mechanism anywhere in this codebase (no such table, router, or frontend UI), and `contact_preference` was write-only even for the three options that stayed (set/read back to the candidate, never read by any company-facing code path). Rather than build a messaging feature right now, the user asked for three narrower changes:

**Show `full_name`/`email` read-only at the top of the page.** Both already returned by `GET /candidates/{talent_id}`, no backend change needed -- just displayed above the editable fields (`frontend/src/pages/BasicInfoPage.jsx`).

**Dropped `talent.linkedin_url` entirely** -- not hidden, actually removed (migration, model, service, CV-extraction pipeline, tests). Checked the live DB first: 0 of 351 real talent rows had it set, so nothing was lost. Touched: `migrations/008_v2_4_0_to_v2_5_0.sql` (mirrored in `src/database_schema.sql`), `api/models_api.py` (`BasicInfoUpdate`/`TalentOut`), `api/candidate_service.py` (`set_candidate_basic_info`'s allowed-fields set, and the Basic-Info-completeness check in `compute_candidate_completion`, which used to require *both* phone and linkedin_url to be set -- now just phone), `api/routers/candidates.py`'s GDPR export SELECT (added just this session, in item 2 above -- removed again here rather than left stale), `src/candidate_extraction.py`'s `ExtractedBasicInfo`, `api/extraction_service.py`'s `CV_BASIC_INFO_RULE` prompt text, and `prompts/P01_cv_extraction.txt`. Left the *other* "linkedin" mentions in this codebase alone (`ARCHITECTURE.md`, `src/source_classification.py`, `data/source_registry.json`) -- those are about LinkedIn as a prohibited job-board scraping source, an unrelated concept that happens to share a name.

**Removed `in_app_only` from `contact_preference`'s allowed values.** Checked the live DB first here too: exactly 1 of 351 rows had it set. The migration reassigns that row to `'email'` *before* narrowing the CHECK constraint (Postgres won't let you add a constraint existing data already violates). `src/schemas.py`'s `ContactPreference` enum and the frontend's `CONTACT_PREFERENCES` array both dropped the value.

Full backend test suite (177 -- no new tests, existing ones updated for the removed fields) passes. Verified live in a browser: Basic Info now shows name/email read-only, no LinkedIn field, and the contact-preference dropdown only offers email/phone/either.

---

## 2026-07-30 — Admin "Run now" buttons for the three manual/recurring processes; a real background-task/yield-dependency race caught by an end-to-end test

Replaced CLI-only access to `api/reference_data_refresh.py` (ROR/ESCO/CROHO), `api/job_discovery_scheduler.py` (ingestion poll), and `api/job_discovery_runner.py` (recommendation pipeline) with admin-dashboard "Run now" buttons -- `api/admin_tasks.py` (business logic), `api/routers/admin_tasks.py` (endpoints), new `admin_task_run` table (`migrations/007_v2_3_0_to_v2_4_0.sql`). This does **not** change the "never auto-runs" principle stated in each of those three modules' own docstrings: every row in `admin_task_run` still originates from one explicit admin click, same as the CLI command it replaces -- it's a button in front of the same functions, not a scheduler. Each module's docstring updated to reflect that it's now reachable from the dashboard (still never imported at `api/main.py` startup -- the three `run_*_task` wrapper functions in `api/admin_tasks.py` import each module lazily, inside their own function bodies, specifically so that claim stays true).

**Runs execute via FastAPI's `BackgroundTasks`**, so the triggering request returns immediately (202, `{task_run_id, status: "running"}`) rather than blocking -- ESCO alone is ~135 paginated calls, and the job-discovery pipeline makes real, billable Claude calls per subscribed candidate. The frontend (`OverviewTab.jsx`'s new "Manual processes" section, next to the existing "Ingestion health" table) polls `GET /admin/tasks/status` every 5s while any task shows `running`, so the status card updates to succeeded/failed on its own -- first polling pattern in this codebase's frontend (previously zero `setInterval`/polling anywhere).

**A real bug caught by the end-to-end test, not assumed**: the first version of `api/routers/admin_tasks.py` used the shared `Depends(get_connection)` request-scoped connection to call `start_task_run` (which inserts the `'running'` row). FastAPI documents that a yield-dependency's post-yield cleanup (where `get_connection` commits) runs **after** any scheduled `BackgroundTasks` execute, not before. So the background task's own fresh connection (`_finish_task_run`, deliberately separate per the "don't reuse the request's conn" design) tried to `UPDATE` a row the inserting transaction hadn't committed yet -- a silent no-op (`UPDATE` matching 0 rows doesn't raise), leaving every triggered task permanently stuck at `status='running'`. No exception, no test failure until a real end-to-end test (`api/tests/test_admin_tasks.py::test_reference_refresh_croho_real_trigger_end_to_end`, a genuine live CROHO CSV download, chosen as the cheapest real path -- unlike ROR's large zip, ESCO's ~135 calls, or job-discovery's billable AI calls) polled for a final status and never got one. Fixed by having the router open and commit its own short `with engine.begin() as conn:` block inline for the mutating endpoints, instead of the shared dependency -- committed before the function returns, well before `BackgroundTasks` run. Verified for real in a live browser afterward too (admin dashboard, real click, watched "Running..." auto-flip to "Succeeded" via the 5s poll, no page refresh).

**ISCED-F 2013 has no refresh mechanism at all** (static, hand-transcribed from a UNESCO PDF -- unchanged since prior phases). The request listed it alongside ROR/ESCO/CROHO as if all four needed a refresh button; shown instead as a status-only row (`status: "static"`, `refreshable: false`, explanatory note) rather than a fake no-op button or a silent omission.

**Stale-run recovery**: any `admin_task_run` row still `status='running'` after 30 minutes is treated as interrupted (server restart mid-run) and auto-reaped to `failed` before either a status read or a new trigger attempt -- otherwise a crash mid-run would permanently block that task_name from ever running again.

**"Refresh all" is not its own tracked task_name** -- it's a router-level convenience that triggers the 3 reference-refresh task_names as 3 independent rows, so each dataset's own last-run status stays meaningful regardless of trigger path.

Full backend test suite (174 -- 168 existing + 6 new) passes.

---

## 2026-07-30 — GDPR export gap fixed; vacancy_merge.py EDU/CAP/TASK isolation confirmed safe; Phase 4 duplication-risk re-check found nothing broken; conditional phone requirement added

Four follow-on items from the same session as the admin "Run now" work above.

**GDPR export (`GET /candidates/{talent_id}/export`) was missing fields added after it was first built.** Its `talent` SELECT still only named the columns that existed when the endpoint was written -- `phone`, `linkedin_url`, `contact_preference` (Basic Info, Phase 3) and `subscription_updated_at` were silently absent from every export, even though they're real personal-data columns on `talent`. Fixed by adding all four to the SELECT (`api/routers/candidates.py`). EDU/CAP/TASK survey answers were **already** included -- they're just rows in `talent_element_value` like every other category, and the export's `survey_answers` query already selects from that table with no category filter. New test: `api/tests/test_candidate_export_endpoint.py`.

**`vacancy_merge.py`'s trust-ranked conflict resolution was checked for whether it handles EDU/CAP/TASK requirement fields (`required_education`/`required_skills`/`required_occupations`) when a scraped update collides with a company's own submission -- finding: it can't collide, by construction, so there's nothing to fix.** `merge_profile_fields`'s `supported_fields` allowlist only names plain job-posting fields (title/description/location/etc.); `CanonicalVacancyProfile` (the Pydantic model it merges) has no `required_education`/`required_skills`/`required_occupations` fields at all; `vacancy_ingestion.py`'s `incoming_fields` dict (built from a scraper's `RawVacancyRecord`) never populates them either, since a scraper can't extract structured ESCO/ISCED-F-mapped requirement data from job-posting text -- exactly the Phase 5 decision that vacancy-side requirements come only from the company's own search-and-pick workshop submission. That submission lives entirely in `vacancy_element_value`, written only by `POST /vacancies/{id}/workshop`; confirmed both `load_existing_profiles` (`api/ingestion_store.py`) and `upsert_vacancy` (`api/vacancy_store.py`) -- the load/save pair around every poll-cycle merge -- only ever touch the `vacancy` table, never `vacancy_element_value`. The two write paths are fully isolated on both the read and write side. Locked in with a new regression test (`tests/test_vacancy_dedup_merge.py::test_merge_never_touches_edu_cap_task_requirement_fields`) rather than left as an untested assumption, since a future change to either function could silently break the isolation without anything else catching it.

**Duplication-risk re-check (the "suspected, not yet fixed" note from the Phase 1 entry below, 2026-07-29) -- re-verified post-Phase-4, nothing found broken.** `CANDIDATE_DASHBOARD_CATEGORY_ORDER`'s flagged risk ("frontend page order might drift from this backend constant once 8 categories exist") turned out to be moot by construction: `CandidateDashboardPage.jsx` renders `completion.categories` straight from `GET /candidates/{id}/completion`'s response, in whatever order the backend returns -- there never was a second, independently-encoded frontend order to drift from. The two `CATEGORY_LABELS` dicts (backend: all 8; frontend `CategorySurveyPage.jsx`: a deliberate 5-category subset, since EDU/CAP/TASK route to their own dedicated pages) still exist separately, but the 5 overlapping labels match word-for-word today. `MOT_MAX_SELECTIONS = 5` is untouched since Phase 4 and still the only enforcement point, gating all 12 MOT elements correctly. No code changed for this item, per instruction to only fix what's actually found broken.

**Conditional phone requirement**: `phone` is now required only when `contact_preference == 'phone'`, optional otherwise. Enforced in `api/candidate_service.py`'s `set_candidate_basic_info` against the *merged final state* (existing DB row + this request's partial update), not just the fields present in one PATCH call -- since a candidate can set either field alone in separate requests, and a partial update leaving `contact_preference` untouched must still be checked against whatever `phone` already is (and vice versa). Raises `ValueError` -> `422` (`api/routers/candidates.py`). Frontend (`BasicInfoPage.jsx` + shared `TextField`, `frontend/src/components/formFields.jsx`) shows a dynamic `*` indicator and sets the native HTML `required` attribute based on the currently-selected `contact_preference`, not a static label -- verified live in a browser: indicator/required toggles on selection change, an empty-phone submit is blocked client-side by the browser's native validation before it ever reaches the backend, and a real submit with both fields set saves successfully.

Full backend test suite (177 -- 174 existing + 1 GDPR-export + 1 merge-isolation + 1 conditional-phone) passes.

---

## 2026-07-30 — Phase 5 of Education/Capabilities/Task History build: vacancy-side required education/skills/experience, matching symmetry with the candidate side

**A real, pre-existing bug found while building this: `VacancyWorkshopPage.jsx`'s category list omitted EDU entirely.** `const categories = ['PRACT', 'ENV', 'CAP', 'TASK', 'TEAM', 'CAREER', 'MOT']` -- harmless while EDU had no active elements, but would have silently hidden the entire Education requirement section the moment EDU-HISTORY went live (Phase 4), exactly the "future category-order drift" risk flagged back in the Phase 1 entry above. Fixed by adding 'EDU'.

**Search-and-pick, not AI mapping, for vacancy-side requirements.** Candidate-side CAP/TASK/EDU (Phase 2/4) use AI mapping with a confidence score, because a candidate is self-reporting an ambiguous personal fact in their own words. A company specifying a REQUIREMENT is different: it's authoritatively defining what the role needs, so a direct search-and-pick against the real ESCO/ISCED-F reference data (new `GET /reference/skills`, `/occupations`, `/isced-fields`) is both more appropriate and simpler -- no confidence/requires_confirmation handling needed on this side at all. Institutions/programs search stays candidate-only (education history is personal); skills/occupations/isced-fields opened to companies too (`require_role("candidate", "company", "admin")` on the whole `/reference` router, simpler than splitting auth per-endpoint for no real benefit).

**Consolidated reference-dataset loading into one module.** `api/mapping_service.py` used to have its own private `_load_esco_skills`/`_load_esco_occupations`/`_load_isced_narrow_fields`; these moved to `api/reference_search.py` (now public: `load_esco_skills` etc.) since Phase 5's new search functions need the same data -- `mapping_service.py` now imports them back rather than maintaining a second copy of the same loading logic.

**Vacancy-description AI extraction (P04) scoped to exclude EDU/CAP/TASK, mirroring Phase 3's CV-extraction fix exactly.** `VACANCY_EXTRACTION_EXCLUDED_CATEGORIES = {EDU, CAP, TASK}` (`api/extraction_service.py`) -- a vacancy-description extraction can only ever produce a low-confidence guess at a required-skill/occupation/field-to-ESCO/ISCED-F mapping, with no confidence gate at all (unlike the candidate-side AI mapping, which at least has one) -- strictly worse than the candidate-side case Phase 3 already fixed, so the same reasoning applies more urgently here, not less. `prompts/P04_vacancy_extraction.txt`'s own ACTIVATION RULES section, which Phase 3 had already updated once, needed updating *again* here since it explicitly said "extract required skills/experience/education as vacancy content here" -- exactly the opposite of this decision. Also caught and fixed a real inaccuracy in that same Phase 3 edit: it referenced `unmapped_terms`, a field that only exists on `CandidateExtractionResult`, not `VacancyExtractionResult` (whose real fields are `extracted_elements`/`unanswered_element_ids`/`review_flags`) -- found by checking the real Pydantic model, not by re-reading the prose.

**Shared `RequirementListEditor` component, not three near-identical copies.** CAP-SKILLS/TASK-EXPERIENCE/EDU-HISTORY's vacancy editors are all "repeatable list, search-or-select a code, set an optional level, set required/preferred" -- one parameterized component (`frontend/src/components/RequirementListEditor.jsx`) handles all three, in two picker modes: "search" (ESCO, too large to list) and "select" (ISCED-F's 29 fields, small enough to show directly, better UX as a dropdown than a search box when every option already fits). `formFields.jsx`'s `Select` was extended to accept `{value, label}` option objects (backward-compatible with its original plain-string usage) specifically so ISCED-F codes don't have to be shown to the user as bare, meaningless codes.

**Real, complete, end-to-end verification, not just persistence.** Beyond the unit/integration tests (168 total, 152 existing + 16 new -- reference-search endpoint tests, vacancy-extraction-scoping tests, vacancy-requirement-persistence test), walked the whole loop in a real browser: registered a company, created a vacancy, added a required skill (SQL, real ESCO URI, searched live against real data), a required occupation (software developer, real ESCO URI), and a required education field (ISCED-F 061/ICT + bachelor's, picked from the real 29-entry list fetched live from the backend), submitted, and confirmed the exact persisted JSON via direct DB read. Then closed the loop with a real weighted match (`run_match`, real `MatchConfiguration`, real comparator dispatch) between that exact vacancy and a candidate with matching CAP-SKILLS/TASK-EXPERIENCE/EDU-HISTORY data: CAP and EDU both scored 100%/100% (exact URI/code + level match), TASK scored 100% on the one comparable item (occupation) with coverage correctly at 50% since the browser test never set a vacancy-side TASK-YEARS requirement -- coverage reflecting real missing data, not a bug.

Full test suite (168 -- 152 existing + 16 new) passes.

---

## 2026-07-30 — Category weight rebalance: equal 12.5% across all 8 categories (the deferred decision from Phase 1/4, now made)

**Decision: equal weighting, 12.5% per category, all 8.** Previously PRACT/TEAM/CAREER/MOT/ENV at 20% each, EDU/CAP/TASK at 0% (a placeholder, not a judgement -- see the Phase 1 and Phase 4 entries above). Updated in all three locations that must stay in sync (no runtime single-sourcing between them):
- `src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS` -- the real fallback every scraped/ingested vacancy actually uses.
- `frontend/src/pages/VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS` -- the company-direct submission form's starting point.
- `data/public_weight_profile.json` -- still unwired to any real code path (confirmed again, unchanged since the Phase 0 finding), kept in sync by hand for whoever eventually wires it in. Bumped to v2.3.1.

**Why equal, not recruiter-weighted toward CAP/TASK/EDU:** `DEFAULT_PUBLIC_WEIGHTS` specifically backs vacancies with *zero human review* (scraped/ingested postings a company never touched). An uneven split there would silently impose an editorial judgement -- "skills matter more than motivation" or similar -- on postings nobody actually validated. The company-direct form's default is the same value for consistency, but companies remain free to customize it immediately; only the scraped-vacancy path is genuinely unreviewable.

**Recruiter-weighted alternative, logged as a potential future preset, not a default.** Considered and explicitly rejected as the *default*, but worth keeping on record as an opt-in a company could apply when customizing one specific vacancy's weights, since it reflects a real, common hiring intuition (skills/experience as the most direct, verifiable "can they do the job" signal, education as a comparatively weak signal for most roles):
```
PRACT 15 / CAP 15 / TASK 15 / EDU 10 / TEAM 11.25 / CAREER 11.25 / MOT 11.25 / ENV 11.25
```
**Revisit when**: if/when a "suggested weight presets" UI ever gets built for the vacancy customization flow (not currently planned), this is the first candidate preset to offer alongside "equal across all 8."

**Verified three ways, not just eyeballed:**
1. `MatchConfiguration`'s own real field validator (`weights_must_sum_to_100`, `src/schemas.py`) accepted `DEFAULT_PUBLIC_WEIGHTS` directly -- the actual production sum-to-100 enforcement, not a standalone check reimplementing the same rule a second time.
2. New test `test_default_public_weights_are_equal_across_all_8_categories_and_sum_to_100` (`tests/test_canonical_vacancy.py`) asserts the real constant (not just the already-tested dead JSON file) covers exactly `Category`'s 8 members at 12.5 each.
3. A real match run: created a real company + vacancy with the new weights, answered one real vacancy-side element (`PRACT-SPONSOR`) aligned with real candidate Jordan Vance's existing answer, and ran a real `POST /vacancies/{id}/match`. Confirmed `category_weight: 12.5` appears against all 8 categories in the real result, and PRACT correctly scored 100% at its 12.5% weight from that one answered pair. **Note on scope**: candidate *completion percentage* (the "Your profile" dashboard number, `compute_candidate_completion`) does not use `category_weights` at all -- it's a plain unweighted answered/active ratio with no vacancy in scope -- so there was nothing there to break or usefully re-verify; the real thing worth checking was a weighted match, which is what this instead confirms.

Full test suite (164 -- 163 existing + 1 new) passes.

---

## 2026-07-30 — Phase 4 of Education/Capabilities/Task History build: frontend, 8-category reorder, and a real cross-category submit bug caught by browser testing

**Career category kept after a spec inconsistency was caught before building against it.** The original Phase 4 order list (Basic Info -> Education -> Practical fit -> How you work -> What drives you -> Your ideal environment -> Capabilities -> Task History) omitted "Where you're headed" (CAREER) entirely, an existing live category with real candidate data (confirmed against a real test candidate, Jordan Vance). Flagged to the user before writing any dashboard/backend code against the literal 8-item list; confirmed as an oversight, not intentional. Final order: Basic Info (excluded from completion %) -> Education -> Practical fit -> How you work -> Where you're headed -> What drives you -> Your ideal environment -> Capabilities -> Task History -- 8 real Fit Dictionary categories plus Basic Info as a separate, uncounted first step.

**Basic Info surfaced as its own dashboard concept, not a 9th category row.** `compute_candidate_completion` (`api/candidate_service.py`) returns a sibling `basic_info: {label, complete}` field alongside `categories`, computed directly from `talent.phone`/`linkedin_url` (both non-null = complete; `contact_preference` not counted since it always has a real DB default). Kept structurally separate from the `categories` array specifically so it can never be accidentally swept into `overall_percent_complete`'s denominator by a future generic loop over "all dashboard cards."

**`data/fit_dictionary_starter.json`'s 5 Phase-1 elements flipped to `active: true` in the live DB** (EDU-HISTORY, CAP-SKILLS, TASK-EXPERIENCE, TASK-YEARS, PRACT-WORKTYPE) via `seed_fit_dictionary()`'s existing upsert -- the "revisit when" condition PROJECT_NOTES already flagged for this (full extraction+frontend loop built) is now met. Confirmed consequence, not a surprise: `PRACT-WORKTYPE` newly counting toward Practical fit's `active_item_count` means existing candidates' displayed Practical-fit completion drops until they answer it (real example: Jordan Vance's PRACT went from complete to 85.7%) -- exactly the tradeoff the earlier entry predicted, now accepted as the intended cost of shipping the feature.

**A second work-type comparator key had no registered frontend editor at all.** `PRACT-WORKTYPE`'s `comparator_key` is `work_type_set` (employment type: full-time/internship/student-job/part-time) -- distinct from the pre-existing `work_mode_set` (work *location*: on-site/hybrid/remote). `frontend/src/components/valueEditors/index.jsx`'s `VALUE_EDITORS` map only had the latter; without a fix, activating PRACT-WORKTYPE would have silently hit the "no editor registered" fallback the moment a real candidate reached Practical fit. Found by reading the existing editor map against the new element's real comparator_key, not by running into it live -- added `WorkTypeSetCandidate`/`WorkTypeSetVacancy` before activating the element.

**Three genuinely new dedicated pages, not the existing generic `CategorySurveyPage`.** Education/Capabilities/Task History each hold repeatable, multi-field structured entries (a list of `{level, institution, program, dates, status}` objects, etc.) -- no existing editor combined "true array" + "structured multi-field row" + "add/edit/delete" (`PRACT-LANG`'s map-shaped value and `CAREER`'s flat-string-array `SemanticOverlapEditor` were the closest partial precedents, neither sufficient). Built as three new page components (`EducationPage.jsx`/`CapabilitiesPage.jsx`/`TaskHistoryPage.jsx`) sharing extracted `formFields.jsx` primitives (`TextField`/`Select`/`CheckboxGroup`/`DateField` -- moved out of `valueEditors/index.jsx` rather than copied a third time) and a new `SearchAutocomplete.jsx` component.

**New institution/programme search endpoints, confirmed not to already exist.** `GET /reference/institutions` and `GET /reference/programs` (`api/reference_search.py`, `api/routers/reference.py`) back Education's autocomplete against the ROR/DUO datasets Phase 0 bundled -- verified via a real research pass that no such endpoint existed anywhere before building it (Phase 2's `map-skill`/`map-occupation`/`map-program` are AI *classification* endpoints, not name *search*, and were confirmed unconsumed by any frontend code until this phase). The same local text-similarity shortlist logic Phase 2's `mapping_service.py` used was extracted into a shared `api/text_search.py` rather than copied a second time -- `mapping_service.py` now imports it too.

**TASK-YEARS auto-computed server-side, with an overlap-merge algorithm, never re-derived in JS.** `src/task_years.py`'s `compute_total_years_experience()` merges overlapping job date ranges before summing (so two concurrent part-time jobs don't double-count that stretch), floors to whole years, and is wired into `POST /candidates/{id}/survey` (`api/routers/candidates.py`): submitting `TASK-EXPERIENCE` auto-derives and inserts `TASK-YEARS`; submitting `TASK-YEARS` directly is rejected with a 400. The frontend's Task History page deliberately does not reimplement this math for its "total years" display -- it re-fetches the backend's own computed value after each save, specifically to avoid a second, independently-maintained copy of the same algorithm silently drifting from the real one.

**A real cross-category submit bug, found only by browser-testing the pages in the order a real candidate would use them.** `CategorySurveyPage.jsx`'s prefill has always merged *every* category's saved answers into local state (`GET .../survey-values` returns all categories at once), and its submit has always resent the *entire* merged `answers` object, not just the current page's category -- previously harmless (extra resubmitted values were just redundant, unchanged writes). The moment TASK-YEARS existed and could be directly rejected, this became a real, visible bug: saving Practical fit (or any other existing category) after Task History had ever been answered sent TASK-YEARS back along with it and the whole submission 400'd. Caught by actually walking through Basic Info -> Education -> Capabilities -> Task History -> Practical fit in a real browser, in that order, not by unit tests (which each test one category/endpoint in isolation and wouldn't reproduce a cross-category interaction). Fixed at the actual root cause -- `handleSubmit` now filters `answers` down to this page's own `categoryElements` before submitting -- rather than loosening the backend's rejection rule, since the backend's guarantee is exactly correct and the frontend's "resubmit everything" habit was the real latent bug.

**Local dev environment: Node.js was not installed at all, and a Dropbox-sync race broke Vite's dev server.** Flagged to the user rather than silently working around; installed Node.js LTS via winget with explicit go-ahead. Separately, `frontend`'s home inside a Dropbox-synced folder causes Vite's dependency-optimizer to intermittently EBUSY-fail (Dropbox's sync agent races the temp-directory rename) -- reproduced twice, not a fluke. Fixed by pointing `cacheDir` (`frontend/vite.config.js`) at the OS temp directory instead of the default `node_modules/.vite`, a permanent fix for anyone running this project's dev server from this folder, not a session-specific hack.

Full test suite (163 -- 152 existing + 11 new: reference-search endpoint/unit tests, task_years unit tests) passes. Real browser walkthrough covered: registration, Basic Info save, Education (institution autocomplete against real ROR data, programme AI-mapped to ISCED-F with a real high-confidence match, submit, prefill), Capabilities (skill AI-mapping including a real no-match case, submit), Task History (two overlapping jobs, confirmed the displayed computed total correctly merged the overlap rather than double-counting), Practical fit regression (including the new PRACT-WORKTYPE editor), and the cross-category submit bug above, found and fixed live.

---

## 2026-07-30 — Phase 3 of Education/Capabilities/Task History build: narrowed CV extraction scope, a gap discovered (Basic Info had no endpoint at all), and a real prompt-leak bug caught by a test

**Scope gap found and filled: Basic Info had zero API surface.** Phase 1 only
added `phone`/`linkedin_url`/`contact_preference` as raw `talent` columns
(migration + DB schema) -- no endpoint anywhere read or wrote them, and
`src/schemas.py`'s own `Talent` model didn't have the fields either. Since
Phase 3 asks CV extraction to cover Basic Info, and there was nowhere for an
extracted (or manually entered) value to land, this had to be built now, not
deferred to Phase 4's frontend work: `ContactPreference` enum + `Talent`
fields (`src/schemas.py`), `TalentOut`/`BasicInfoUpdate` (`api/models_api.py`),
and `PATCH /candidates/{talent_id}/basic-info` (partial update -- a field
omitted from the request is left untouched, `contact_preference` can never
be written as SQL NULL since it's NOT NULL at the DB level). Flagging this
here rather than treating it as silently in-scope, since it wasn't itemised
in any of the original phase list.

**Hard code-level category allowlist, not an active-flag side effect.**
`api/extraction_service.py`'s new `CV_EXTRACTION_CATEGORIES = {PRACT, EDU}`
filters the dictionary before it ever reaches the CV extraction prompt --
CAP/TASK (and CAREER/MOT/ENV/TEAM) are structurally absent regardless of
their `active` flag. This matters because the *previous* reason CAP/TASK
never appeared in CV extraction was incidental (they were `active: false`,
so `load_dictionary()` never returned them) -- once Phase 4 flips them
active for manual entry, that accidental protection disappears. The
allowlist is the real, permanent guarantee "must never attempt CAP/TASK
extraction" asked for.

**A second leak found only by a real test, not by reading the code twice.**
The first version of the scoping test failed -- correctly -- because
`data/mapping_memory.json` (an illustrative-only sample file with a
`CAP-SQL` alias entry) was still being sent to the CV extraction prompt
*unfiltered*, and `CV_ELEMENT_ID_RULE` treats mapping memory as an equally
valid source for `element_id` as `fit_dictionary` itself. Category-scoping
the dictionary alone was not airtight: a CAP alias could still reach the
model through the side door. Fixed by filtering `_mapping_memory()` to only
entries whose `canonical_element_id` is a key of the dictionary actually
being sent (works the same way for vacancy extraction, a no-op there today
since vacancies aren't category-scoped). **Lesson, same shape as Phase 2's
Excel/KDevelop finding**: a scoping/confidence guarantee is only as strong as
every path that could leak around it, and the second path here was only
found because a real test asserted the actual dictionary JSON sent to the
model, not because the code was re-read more carefully.

**Basic Info extraction is phone/linkedin_url only, never contact_preference.**
A CV essentially never states how someone wants to be contacted; extracting
or guessing it would violate the same "explicit information only" rule
`P01_cv_extraction.txt`'s system role already states for personality/
motivation/nationality/etc. It stays manual-entry-only via the new PATCH
endpoint, defaulting to `'email'`.

**Known minor limitation, not fixed here: extracted education dates
sometimes get invented day/month granularity.** A real API test CV stating
only "2019-2021" for a degree came back with `start_date: "2019-01-01"`,
`end_date: "2021-12-31"` -- plausible, but the day/month weren't actually
stated. `EDU-HISTORY`'s `candidate_value_schema` (Phase 1) requires full
`YYYY-MM-DD` strings with no partial-date option, so there's no schema-level
way for the model to say "only the year is known." Not a Phase 3 regression
(the schema shape predates this phase) and not fixed here since it would
mean revisiting a Phase 1 schema decision without being asked to. **Revisit
when**: if this proves to matter in practice (e.g. mis-sorted timelines),
consider a nullable day/month or a `precision: "year"|"month"|"day"` field
alongside `start_date`/`end_date`.

**Real API verification**: a real CV (contact info, two degrees, one job
with SQL/Python/"led a team" language, an explicit no-sponsorship-needed
statement) extracted correctly through `run_cv_extraction` against the real
41-element live dictionary plus a manually-activated `EDU-HISTORY` for
testing (still `active: false` for real candidates until Phase 4, per the
Phase 1 entry above): Basic Info and Practical fit answered correctly, all
skill/task/education-programme terms routed to `unmapped_terms` (never
invented as CAP/TASK), and citizenship-adjacent language correctly excluded
per `review_flags`.

**A second, unrelated regression caught only by the full suite**: an earlier
`Edit` call meant to add `ContactPreference` after `SubscriptionSource` in
`src/schemas.py` matched only a prefix of `SubscriptionSource`'s real body
(missing its last member, `PREMIUM_REQUEST_APPROVED`, which a narrower
earlier `grep -A6` had not shown) -- the replacement spliced `ContactPreference`
in before that line, silently reassigning it to the wrong enum. Caught
immediately by the full test suite (Premium-request approval flow), not by
re-reading the diff. Fixed by reading the complete original class body
before editing. **Lesson**: read the *whole* section being edited, not a
grep excerpt of it, before writing an old_string that assumes it's complete.

Full test suite (152 -- 146 existing + 6 new) passes.

---

## 2026-07-30 — Phase 2 of Education/Capabilities/Task History build: AI mapping service, and a real confidence-trust bug found via live testing

**Two-stage design: cheap local pre-filter, then a real semantic judgement call.**
ESCO has 13,485 skills and 2,942 occupations -- far too many to hand Claude in
one prompt (same reasoning as `api/extraction_service.py`'s own value-schema
fix). `api/mapping_service.py`'s `_shortlist()` narrows each call to ~20
candidates using plain normalised-text similarity (`difflib.SequenceMatcher`
+ `vacancy_utils.normalise_text`) -- the *same mechanism*
`src/ind_sponsor_registry.py`'s `SponsorRegistry.lookup()` already uses for
company-name fuzzy matching, reused rather than reinvented. Claude then makes
the real meaning-based judgement (not just spelling) from that shortlist,
plus a confidence score. ISCED-F 2013 has only 29 narrow fields -- small
enough to send in full, no shortlist stage needed for programme mapping.

**`requires_confirmation` reuses the "never silently accept" pattern
literally, not just in spirit.** It mirrors
`CompanySponsorshipSignal.human_review_required` (same file as
`SponsorRegistry`, above) -- true whenever nothing matched, or confidence is
below `MAPPING_CONFIDENCE_THRESHOLD` (env-var overridable, default 0.7, same
"tunable, not hardcoded" precedent as `RECOMMENDED_REFRESH_INTERVAL_DAYS`
from Phase 0). The candidate must confirm or correct before it's treated as
settled -- this endpoint never persists anything (same "draft only" shape as
`extract-cv`).

**ISCED-F granularity decision: narrow fields (3-digit, 29 entries), not
broad (2-digit, 11) or detailed (4-digit, 80).** `tagged_list_overlap_education`
(Phase 1) does exact-string tag matching, not hierarchy-aware partial
matching -- broad would be too coarse to mean much (e.g. one code covers both
Marketing and Law), detailed would make an exact match between a vacancy's
stated requirement and a candidate's specific programme improbably strict.
Narrow is the standardisation level for **both** sides -- this decision must
carry through to Phase 5's vacancy-side ISCED-F extraction unchanged, or the
comparator's exact match will silently stop working across the two sides.

**DUO/CROHO's own `ISCED` column checked and rejected as a mapping
shortcut.** The bundled `data/reference/duo_ho_opleidingsoverzicht.csv` (Phase
0) has a real `ISCED` column, which looked at first glance like it might let
programme->ISCED-F skip AI mapping entirely for Dutch programmes. Checked
directly before assuming reuse (same discipline as the Phase 1
`fit_element_proposal`/`fit_element_alias` check): only 730 of 6,807 rows
(~11%) have it populated, and populated values ("81", "0", "914", "923")
don't fit ISCED-F 2013's actual code shape at all (valid codes are 2/3/4-digit
strings from a fixed ~120-entry set; "81" isn't one). This is very likely a
different, uncatalogued DUO-internal or ISCED-1997 scheme, not usable as a
free crosswalk. Real AI mapping from free text is used for all programmes,
Dutch or not, rather than a fragile partial shortcut for a subset.

**`src/normalisation_registry.py` / `prompts/P03_element_normalisation.txt`
flagged as now *doubly* obsolete -- not fixed, just flagged.** Already
dead/unwired (found during the Phase 1 duplication sweep: zero real callers
besides its own test). Now also architecturally superseded: its whole design
premise -- mint one new canonical Fit Dictionary element per distinct
skill/task (`CAP-{SLUG}`) -- directly conflicts with the Phase 1 redesign,
where CAP/TASK/EDU are each a *single* repeatable-array element instead.
Worth deleting alongside the next real touch of either file, rather than
carrying two competing designs indefinitely.

**A real defect caught only by calling the real API, not by clean test
output.** First real run of `map_skill_to_esco("Excel")` returned
`matched_code` = ESCO's "KDevelop" (a C++ IDE) at confidence 0.9 --
confidently wrong, and `requires_confirmation=False` despite Claude's own
reasoning admitting "not a perfect semantic match." ESCO genuinely has no
Microsoft Excel entry (confirmed by a direct substring search across all
13,485 skills), so the shortlist reaching Claude was mostly spelling-adjacent
noise (KDevelop, C#, Xcode, Perl) -- and self-reported confidence alone
didn't reliably reflect that. Fixed at two levels, since a prompt-only fix
can't be trusted to hold on every future call:
1. Code-level backstop (`api/mapping_service.py`'s `_to_result`): any
   `matched_code` not literally present in the list Claude was given is
   discarded outright, regardless of confidence. Catches invention; does not
   by itself catch "picked a real shortlist item that isn't a real match"
   (the Excel/KDevelop case), since KDevelop genuinely was in the shortlist.
2. Prompt-level (`prompts/P22_skill_esco_mapping.txt` /
   `P23_occupation_esco_mapping.txt`): added a HARD RULE anchoring confidence
   to genuine-match judgement ("if your own reasoning admits the pick is
   imperfect or a different real-world thing, that is a below-0.5 case, not
   0.5-0.8") plus the concrete Excel/KDevelop worked example. Re-verified
   with a real follow-up call: `map_skill_to_esco("Excel")` now returns
   `matched_code=null`, confidence 0.1, `requires_confirmation=True`; known
   real matches (SQL, "Software Engineer"->"software developer") still
   confirm confidently and correctly. **Lesson**: an AI's own confidence
   score is not self-verifying -- when it can be checked against ground
   truth (here, "does ESCO even have this concept"), check it before trusting
   the number, the same way `ai_client.py`'s `max_tokens` truncation check
   already refuses to trust "no exception was raised" as proof of a complete
   response.

**Endpoints**: `POST /candidates/{talent_id}/map-skill|map-occupation|map-program`
(candidate-authenticated via the existing `require_candidate_self_or_admin`,
rate-limited 60/hour, never persist). Consolidated the talent-existence
check into one `_require_candidate()` helper shared with `extract-cv` rather
than leaving a second copy of the same query right after the CAP/TASK
duplication feedback above -- caught before it became a fifth instance of
that exact failure mode, not after.

Full test suite (146 -- 133 existing + 13 new) passes.

---

## 2026-07-29 — Phase 1 of Education/Capabilities/Task History build: schema + Fit Dictionary + comparator, and a rule found duplicated in 4 separate places

**`fit_element_proposal`/`fit_element_alias` -- confirmed not reusable, not
touched.** Read both tables' real DDL before deciding anything.
`fit_element_alias` maps a free-text synonym to an *existing* Fit Dictionary
`element_id` (FK-constrained to `fit_element`) -- built for resolving
synonyms of the ~40 fixed canonical questions, not for mapping a candidate's
free-text skill to an external ESCO code. No confidence-score column at all.
`fit_element_proposal` is for proposing a brand-new *canonical* Fit
Dictionary element (extending the shared taxonomy itself), gated to CAP/TASK
only by its own check constraint, with mandatory human-review fields
(`reviewed_by`/`reviewed_at`) -- a taxonomy-governance workflow, not a
per-candidate-entry AI-confidence mechanism. Neither has a `talent_id`.
Adapting either would mean rewriting it into something else entirely, which
defeats "reuse, don't build a third system." **Decision**: store each
ESCO/ISCED mapping's code + confidence directly inside the same
`talent_element_value.value` JSON blob that already holds every other
element's answer -- no new table, reusing the existing flexible-JSON
mechanism `PRACT-LANG` already relies on.

**Comparator generalization -- built, not just proposed.** Added
`score_tagged_list_overlap()` to `src/practical_comparators.py` (a new
function; `score_language` and the other existing comparators are
untouched), merging `score_language`'s leveled single-tag lookup with
`score_set_compatibility`'s overlap-matching rule into: does the candidate
have at least one `{"tag", "level"}` entry that satisfies at least one
required entry of the same shape? Unleveled (pure tag overlap) when
`level_order=None`; leveled (exact-or-above aligned, one-below weak,
further-below misaligned) otherwise. Serves all three new repeatable
categories via `api/comparators_dispatch.py`'s three new dispatch keys,
each mapping that category's own richer entry shape into the same flat
`{tag, level}` pair before calling the one shared function:
- `CAP-SKILLS` (`tagged_list_overlap_skills`) -- leveled by
  `SKILL_PROFICIENCY_LEVEL` (beginner/intermediate/advanced/expert).
- `TASK-EXPERIENCE` (`tagged_list_overlap_occupation`) -- unleveled
  (occupation-domain presence only; years of experience is the *separate*
  `TASK-YEARS` element below, reusing `ordinal_requirement` as-is with zero
  new code, exactly as scoped).
- `EDU-HISTORY` (`tagged_list_overlap_education`) -- leveled by
  `EDUCATION_LEVEL` (secondary/vocational/bachelor/master/phd), tag = the
  ISCED-F field code (falling back to the raw program text if unmapped).
An entry with no ESCO/ISCED mapping yet (or one the candidate hasn't
confirmed) still gets literal-text comparability via its own raw free-text
fallback -- never silently excluded from matching. 10 new real unit tests in
`tests/test_tagged_list_overlap.py` cover the leveled/unleveled/overlap/
fallback behavior directly.

**Repeatable entries: one Fit Dictionary element per category, JSON-array
value** -- `EDU-HISTORY`, `CAP-SKILLS`, `TASK-EXPERIENCE` each hold a list of
structured entries in their single `talent_element_value.value`. Confirmed
this needs zero new persistence code: `POST /candidates/{id}/survey` and
`GET .../survey-values` already treat `value` as opaque JSON with no
per-element key validation, so the existing versioned-insert and resume-fill
logic (see the earlier per-category survey-page entry above) works
unchanged for an array-shaped value exactly as it does for `PRACT-LANG`'s
map-shaped one. EDU was originally going to be a single non-repeatable
record (my own ambiguous first draft) -- corrected to repeatable before any
code was written, since a candidate can have multiple degrees and a
single-entry model can't represent "graduated on one degree, in progress on
another" at the same time.

**A rule found duplicated in four separate places, only one of them
correct.** CAP/TASK originally required `activation_policy='vacancy_activated'`
(the pre-Phase-1 design: CAP/TASK would only activate once a specific
vacancy requested that skill/task, mirroring TEAM). Candidate-entered
skills/work history need to be always answerable, independent of any
vacancy -- like PRACT/CAREER/ENV -- so this needed to become `'always'`.
Fixing it surfaced that the *same* rule was implemented four times, fully
independently, with no single source of truth:
1. `fit_element`'s own DB check constraint (`fit_element_check`) -- swapped
   via `migrations/006_v2_2_0_to_v2_3_0.sql`, a targeted allow-list value
   change, not a broad relaxation (MOT's `fit_element_check1` and TEAM's
   `fit_element_check2` are separate constraints, untouched).
2. `schemas.py`'s `expected_activation_policy()`, enforced by every
   `FitElement`'s own `model_validator` -- fixed, this is now the one real
   source of truth the other two below should have been calling all along.
3. `src/dictionary_tools.py`'s `validate_dictionary()` had its own *third*,
   fully independent copy of the same three per-category rules (CAP/TASK,
   MOT, TEAM) -- and turned out to be dead code once traced: every caller
   reaches it only via `load_fit_dictionary()`, which already runs
   `FitElement.model_validate()` first, so a violation would always raise
   there before ever reaching this "check." Removed rather than fixed a
   second time, since keeping it "in sync by hand" is exactly the failure
   mode this note is about.
4. `src/normalisation_registry.py`'s `build_approved_dynamic_element()`
   hardcoded the literal directly, despite its own docstring already
   promising activation is "system-derived, never reviewer-selected" -- now
   actually calls `expected_activation_policy()` instead of asserting that
   and not doing it.
Caught only because the full test suite was run after the change, not
assumed clean from "the migration applied without error." **Lesson,
consistent with the CAP:30/TASK:25 weighting bug from 2026-07-27**: a
business rule expressed as a DB constraint should have at most one
*additional* enforcement point in application code (ideally zero, with
everything else calling that one function) -- every independent
reimplementation is a place the next change can update three copies and
miss the fourth.

**Follow-up per explicit user feedback: broadened the sweep past the 4 places
above.** Told directly that since this is the *second* rule found duplicated
across files (after the CAP:30/TASK:25 weighting bug), a broad repo-wide grep
for the rule's other encodings -- not just the two places raised -- should
happen before calling a fix "complete," including data fixtures, tests, and
AI prompt files, not just application code. A case-insensitive grep for
CAP/TASK near `vacancy_activated` across the whole repo (21 files matched)
found 4 more stale copies beyond the 4 already fixed:
- `data/fit_dictionary_demo_extensions.json` -- 3 entries (`CAP-SQL`,
  `CAP-FORECASTING`, `TASK-ANALYSE-OPERATIONAL-DATA`) still
  `vacancy_activated`. Confirmed zero application-code references (dead,
  same category as the earlier `public_weight_profile.json` precedent) --
  fixed anyway, since a stale fixture is exactly the kind of thing someone
  copies from later.
- `data/fit_element_templates.json` -- the `CAP-DYNAMIC`/`TASK-DYNAMIC`
  minting templates (referenced conceptually, not by code path, from
  `normalisation_registry.py`'s dynamic-element minting). Also dead by
  reference-check; fixed.
- `prompts/P14_activation_status_audit.txt` -- an AI audit-prompt's CHECK
  list item still said CAP/TASK are `VACANCY_ACTIVATED`. Grepped for its own
  filename across `api/` and found no live caller -- unwired/dead. Fixed
  anyway for the same reason as the JSON fixtures.
- `prompts/P04_vacancy_extraction.txt` -- **the one exception that was
  actually live.** Same stale "CAP/TASK items may be VACANCY_ACTIVATED after
  human confirmation" framing, but `api/extraction_service.py:257`
  (`build_vacancy_extraction_prompt`) loads this file verbatim as the real
  prompt for every live vacancy-description extraction call -- confirmed via
  direct grep of `extraction_service.py`, which has no other hardcoded copy
  of the rule. Left uncorrected, every real vacancy extraction would have
  kept nudging the AI toward drafting a CAP/TASK activation step that no
  longer exists. Fixed to state CAP/TASK are always active candidate-side,
  and to note the vacancy-side required-skills/experience/education fields
  (Phase 5, not yet built) are a separate mechanism.
Full test suite re-run after all 4 additional fixes: still 133 passed, 0
failed. **Practice going forward, not just this once**: when a rule turns
out to be enforced in more than one place, grep broadly (code, data/JSON
fixtures, tests, prompt files) for every other encoding before calling the
fix complete, and check each hit against real callers/references rather than
assuming "found in a file" means "found in a live path" -- P04 above is the
concrete example of why that check matters.

**Other rules suspected of the same multi-location duplication risk --
flagged, not fixed.** Noticed while doing the above sweep; none touched yet:
- Candidate-facing category display labels exist in two places:
  `api/candidate_service.py`'s backend `CATEGORY_LABELS` dict and a separate,
  independently-written `CATEGORY_LABELS` dict in
  `frontend/src/pages/CategorySurveyPage.jsx`. Nothing enforces they stay in
  sync today; a label rename on one side silently drifts from the other.
- `api/candidate_service.py`'s `CANDIDATE_DASHBOARD_CATEGORY_ORDER` constant
  is the backend's source of truth for category ordering. Phase 4 of this
  same build will add dedicated Education/Capabilities/Task History pages
  and reorder the survey frontend-side -- real risk the frontend's page
  order (wherever it ends up encoded) drifts from this backend constant once
  8 categories exist instead of 5.
- `MOT_MAX_SELECTIONS = 5` is currently enforced in exactly *one* place
  (`frontend/src/pages/CategorySurveyPage.jsx`), with no backend mirror at
  all. Not a duplication yet, but the precursor to one: the moment a second
  enforcement point is added (e.g. a backend validation on submit), it
  becomes the same one-source-of-truth risk as CAP/TASK activation above if
  the two aren't wired to read from the same constant.
**Revisit when**: touching any of the three areas above for unrelated
reasons -- worth consolidating to a single source at that point rather than
waiting for a third incident to force it.

**All 5 new Fit Dictionary elements seeded `active: false`.** `EDU-HISTORY`,
`CAP-SKILLS`, `TASK-EXPERIENCE`, `TASK-YEARS`, and `PRACT-WORKTYPE` (the new
work-type-preference element) exist as real rows today but are dormant --
`load_dictionary()` only selects `where active = true`, so none of them are
visible via the live `GET /fit-dictionary` (confirmed directly: still
exactly 41 elements exposed, same 5 categories as before). This was a
deliberate, necessary safeguard, not an oversight: `PRACT-WORKTYPE` is a
*new* element on an *already-active, already-live* category -- flipping it
to `active: true` today would immediately raise every real candidate's PRACT
`active_item_count` from 6 to 7 with no way to answer the new item yet (no
extraction/frontend support exists until Phase 3/4), silently *lowering*
their displayed Practical-fit completion on the already-shipped dashboard.
**Revisit when**: each category's full extraction + frontend loop is built
(Phase 3/4) -- flip `active: true` for that category's elements only once
candidates can actually answer them, not before.

Full test suite (133 -- 123 existing + 10 new) passes.

---

## 2026-07-29 — Phase 0 of Education/Capabilities/Task History build: 4 reference datasets bundled locally; a real ESCO pagination bug found and fixed

Built `api/reference_data_refresh.py` (same "never imported by api/main.py, no
scheduler, manually invoked" pattern as `api/job_discovery_scheduler.py`) and
bundled the result under `data/reference/`, ready for Phase 1's schema/Fit
Dictionary work.

**Real record counts, verified directly, not assumed from a "no error" exit**:
- **ROR institutions**: 25,439 (filtered from 132,537 total ROR records to
  those whose `types` includes `"education"` -- ROR's own type taxonomy, not
  a separate `institution_type` field. This is a reasonable proxy for
  "university/college," not a perfect one: ROR doesn't catalogue primary/
  secondary schools at all (its whole scope is research-active
  organisations), so in practice this means universities, colleges, and
  similar research-active institutes, with a handful of non-university
  educational bodies also swept in. Source: ROR's Zenodo concept DOI
  (`zenodo.org/api/records/6347574`, always redirects to the latest release
  -- currently v2.10, 2026-07-20).
- **ESCO skills**: 13,485. **ESCO occupations**: 2,942. Source: the real
  `ec.europa.eu/esco/api/search` REST endpoint (the portal's own bulk-CSV
  download requires an interactive email/click-through flow with no stable
  URL to automate, so the live search API is used instead -- only at refresh
  time, never at request time).
- **DUO higher-education programs**: 6,807 rows. Source: `onderwijsdata.duo.nl`'s
  current "HO Opleidingsoverzicht" CSV -- this is the dataset that succeeded
  the older CROHO-specific downloads DUO used to publish (DUO's CROHO page
  itself now points here). Already carries EQF/NLQF/ISCED columns per row.
- **ISCED-F 2013**: hand-transcribed from UNESCO's own published PDF manual
  (no machine-readable source exists at all for this one -- it's a fixed
  international standard, not a living registry, so `data/reference/isced_f_2013.json`
  has no refresh function and isn't expected to need one).

**Real bug found and fixed before it could quietly ship**: the first
`--refresh esco` run "succeeded" (exit 0, no exception) but silently
collected only 200 of 13,485 skills and 100 of 2,942 occupations. Root
cause: ESCO's `search` endpoint's `offset` query parameter is a **page
index**, not a raw record count -- confirmed empirically (the API's own
`_links.next` href increments `offset` by exactly 1 regardless of `limit`,
and `offset=1&limit=5` returns records 5-9, not records 1-5). The original
code did `offset += limit` (the natural assumption for almost every other
paginated API), which after the first page jumps straight to a page index
equal to the previous *raw offset* -- e.g. requesting "page 100" instead of
"page 1" -- skipping nearly the entire dataset while still returning valid-
looking (but wrong) pages, so nothing ever raised an error. Fixed by tracking
a real `page` counter incremented by 1, with the loop's exit condition
comparing `page * limit` against `total` (matching units) instead of
comparing a page index directly against a record count. Re-ran after the fix
and got the exact real totals above. **Lesson, generalizable beyond this one
API**: "the script exited cleanly with no exception" is not evidence a
paginated bulk-fetch actually completed -- always verify the collected count
against the API's own reported `total`, especially for any paginated
external API whose `offset`/`page` semantics haven't been explicitly
confirmed (raw record offset and page index look identical in the common
case of `offset=0`, and only diverge once you're past the first page).

**Refresh interval is a config value, not hardcoded**: `RECOMMENDED_REFRESH_INTERVAL_DAYS`
reads `REFERENCE_DATA_REFRESH_INTERVAL_DAYS` (env var, default `30`) -- purely
informational today (printed in `--help`, not enforced by any scheduler),
since nothing calls this script automatically.

Full test suite (123) passes -- this phase touched no application code paths,
only added a new standalone script and bundled data files.

---

## 2026-07-29 — Survey split into 5 per-category pages; found and fixed a real MOT-rendering bug and a real CV-extraction reachability regression along the way

Replaced the single long-scrolling `CandidateSurveyPage.jsx` (one page, all 5
categories, reached via `?focus=CATEGORY` + scroll-to-anchor) with
`CategorySurveyPage.jsx`, one per category at `/candidate/survey/:categorySlug`
(slugs centralised in `frontend/src/categorySlugs.js` so the dashboard's links,
`App.jsx`'s route, and the page's own parsing can't drift apart). Submission
logic, endpoints, tri-state/ordinal controls, and the resume-with-existing-
answers fix are all unchanged -- only page structure and navigation changed.

**Real bug caught before shipping, not after**: the new page's category-filter
logic (`elements.filter(e => e.category === category && (e.active ||
answers[e.element_id]))`) applied the same "must be active" condition to MOT
as to the other 4 categories. MOT elements are `CANDIDATE_SELECTED` --
checking the element's own checkbox is *what makes it active* -- so filtering
on `e.active` before anything was ever checked meant zero MOT elements could
ever render. Caught via real browser verification (a fresh candidate's "What
drives you" page showed 0 checkboxes), not assumed correct from the diff.
Fixed by keeping MOT unfiltered (matching the original single-page version's
own `motElements = elements.filter(e => e.category === 'MOT')`, no active
check) and only applying the active-filter to the other 4 categories.

**Real, separate finding, not introduced by this task but caught while
touching this exact code**: the previous task ("remove the standalone Survey
nav link") left `skipToManual()` firing unconditionally whenever a `focus`
query param was present. Since every remaining path into the survey (5
dashboard cards + the Continue button) always carried that param, the
CV-paste/extraction step had already become 100% unreachable through the live
UI -- a real, if narrow, regression from that task. Fixed as part of this
restructure: each category page now checks whether *that specific category*
already has a saved answer (via the same survey-values fetch used for the
resume fix) and only then skips straight to review; a genuinely untouched
category still gets the CV-paste/skip-to-manual choice. Verified for real: a
candidate with existing PRACT answers landed straight on PRACT's review step
(pre-filled), while the same candidate's untouched TEAM and MOT pages
correctly showed the CV-paste step first.

**Verified end-to-end with a real candidate**: clicked into an untouched TEAM
page, skipped to manual, actually moved the ordinal-range sliders (not just
checked their default rendered values -- an unmoved slider never entered
`answers` and correctly submitted nothing), submitted, landed back on
`/candidate`, and saw TEAM flip to "Complete" and overall completion move
from 13% to 17%. Repeated for MOT (checked 2 of 12, answered their detail
questions, submitted) -- MOT flipped to "Complete", overall moved to 24%
(6 of 25 active elements, MOT's 2 selected items now counting toward the
active total). Full test suite (123) passes, unchanged -- this was a
frontend-only restructure with zero backend changes.

---

## 2026-07-29 — Premium nudge on the dashboard now gated by the real match-lane coverage threshold, not an arbitrary percentage

**The real, live number, confirmed by reading it, not assuming it**: `src/match_engine.py:87`'s
`_assign_lane` forces `CLARIFICATION_REQUIRED` (a provisional, not-confidently-scored result)
whenever `overall_coverage < config.minimum_overall_coverage * 100`. That field's default in
`src/schemas.py`'s `MatchConfiguration` is **0.70 (70%)**, confirmed via
`MatchConfiguration.model_fields["minimum_overall_coverage"].default`. It's not just a schema
default nobody uses -- `api/job_discovery_runner.py`'s `make_deterministic_matcher` (the real,
live Job Discovery pipeline) constructs `MatchConfiguration` without ever overriding this field,
so 70% is the actual number governing whether a real candidate's real matches land confidently
or get flagged as provisional today.

**Reused, not re-hardcoded**: `api/candidate_service.get_premium_readiness_threshold_percent()`
reads `MatchConfiguration.model_fields["minimum_overall_coverage"].default` directly -- if that
default ever changes in `src/schemas.py`, this follows automatically with no second edit needed.
`GET /candidates/{id}/completion` now also returns `premium_readiness_threshold_percent` and
`premium_ready` (`overall_percent_complete >= premium_readiness_threshold_percent`). The
candidate dashboard's "Want proactive job matching? That's Premium" value-prop line is now
gated on `premium_ready` -- hidden below the real threshold, shown at or above it. This
replaces what would otherwise have been a second, disconnected magic number.

**One real approximation, made explicit rather than silent**: match_engine.py's real
`overall_coverage_percent` is an `item_importance`-weighted answered/active ratio
(`src/match_engine.py:114-117,144`), not a plain count ratio -- but `item_importance` defaults
to `3` uniformly (`src/schemas.py`) and there is no vacancy in scope on the candidate dashboard
to specify anything else. Under uniform weighting the weighted ratio is mathematically
identical to a plain count ratio, so `compute_candidate_completion`'s existing
`overall_percent_complete` (already used for the per-category cards) *is* the same quantity,
not a second one -- this holds only because `item_importance` isn't candidate-configurable
outside a specific vacancy today. **Revisit if** `item_importance` ever becomes candidate-
visible/configurable independent of a vacancy -- at that point this equivalence would need
re-deriving, not assumed to still hold.

**Verified for real**: a fresh candidate at 0% showed 2 value-prop lines (Premium line
correctly hidden); after answering all 23 real ALWAYS-activated elements (PRACT+TEAM+CAREER+ENV)
to reach a genuine 100%, reloading showed the Premium line. New tests
(`test_premium_readiness_threshold_is_read_from_match_configuration_default`,
`test_premium_ready_flips_as_real_coverage_crosses_the_real_threshold`) confirm both the
no-second-copy property and the flip itself against the real API. Full suite (123) passes.

---

## 2026-07-29 — Candidate dashboard's "Continue" deep link exposed a real gap: the survey page never resumed previous answers — RESOLVED same day

Built the "Your profile" dashboard (per-category completion, `GET /candidates/{id}/completion`)
and the Premium request-and-manually-approve flow (`premium_access_request`, admin
approve/deny, reuses the existing subscription-toggle write via the new
`api/candidate_service.set_candidate_subscription` rather than a second copy of it).

**Real, pre-existing gap this surfaced, not introduced**: `CandidateSurveyPage.jsx` never
fetched a candidate's existing `talent_element_value` rows on load -- `answers` state always
started at `{}`, populated only via a fresh CV extraction or manual entry in the current
session. The dashboard's "Continue: [next incomplete category]" CTA (`?focus=CATEGORY` deep
link) skips straight to the review step and scrolls to that category's section; writing was
always safe (`POST /survey` is a per-element versioned insert -- submitting only PRACT
answers never touched TEAM/CAREER/MOT/ENV rows already stored), but every *other*
already-answered element rendered blank on return -- confirmed for real before fixing:
created a test candidate, saved 3 of PRACT's 6 elements via the real API, reloaded via the
dashboard's Continue link, and all 3 rendered as empty/unselected form controls despite the
DB rows being intact. Not cosmetic -- indistinguishable from data loss to the candidate.

**Fix**: added `GET /candidates/{id}/survey-values`, a thin wrapper around
`api/matching_service.py`'s existing `load_talent_values` (the same latest-per-element-version
query already used at match time -- no new dedup logic). `CandidateSurveyPage.jsx` fetches it
on mount and merges it into `answers` using the same "fetch into the answers-shaped state,
then render via `answers[element_id] || blankAnswer(...)`" pattern `handleExtract` already
used for AI-extracted answers -- reused, not reinvented. Merge order (`{...existing, ...prev}`)
means a fresher local edit or CV extraction already in state always wins, so the pre-fill can
never clobber in-session work regardless of fetch timing. A `prefillLoaded` gate (mirroring
the pre-existing `!elements` dictionary-loading gate) avoids a blank-then-filled flash.

**Verified for real, same repro as the bug report**: same test candidate/answers, reloaded via
the dashboard's Continue link post-fix -- `PRACT-SPONSOR` showed `not_required` selected,
the date field showed `2026-09-01`, and the `hybrid` checkbox showed checked. Unanswered
PRACT fields (country, language) correctly stayed blank -- confirms this pre-fills real saved
answers, not a static/stale snapshot. Full test suite (121) passes; a new real-DB test
(`test_survey_values_returns_latest_saved_answers_for_prefill`) also confirms the endpoint
returns the *latest* version after a re-submit, not the original.

**Also noted**: `api/tests/conftest.py` now disables `slowapi` rate limiting for the whole
test session -- the limiter's in-memory storage is shared across every test file in one
`pytest` process, and enough files call `POST /candidates` that the real 5/hour registration
cap (correct for production) started failing later tests with unrelated 429s once this
task's new tests added a few more registrations. No test exercises rate-limiting behavior
itself, so nothing is silently uncovered by this.

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
