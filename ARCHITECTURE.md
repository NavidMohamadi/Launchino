# Launchino (SHEXON) — Technical Handover Documentation

**Purpose of this document**: a complete map of how the system works, why it was built this way, and where the known rough edges are — written so a new developer can find their way to any specific part of the system without reconstructing the reasoning from scratch.

**Status as of this document**: live in production at `launchino.com`, in closed beta. Core matching, ingestion, extraction, auth, and admin tooling are built and verified against real data. Billing and full legal review are deliberately deferred (see §14).

---

## 1. Product overview

Launchino (legal entity: Shexon BV) is a career-matching platform with two sides:

- **Candidates**: build a structured profile ("Talent Fit Profile") for free, become discoverable to companies searching directly. Optionally subscribe to **Job Discovery** — proactive, automated matching against publicly-discovered vacancies, with AI-generated match explanations.
- **Companies**: post vacancies and search/match against the candidate pool directly (this side is the original, free-to-candidate revenue model — companies pay, not candidates, for direct matching).

The core differentiator is the **Fit Dictionary** — a structured, multi-category matching model (skills, tasks, teamwork, career direction, motivation, environment, and practical constraints like visa/location/work-mode) that deliberately never guesses: every data point is either *answered*, *unknown* (nobody said), or *not applicable*, and the system refuses to report high confidence when coverage is low.

---

## 2. High-level architecture

```
┌─────────────┐      HTTPS       ┌──────────────┐      SQL      ┌─────────────┐
│  Frontend    │ ───────────────▶ │   Backend     │ ─────────────▶│  Database    │
│  React+Vite  │ ◀─────────────── │   FastAPI     │ ◀─────────────│  Postgres    │
│  (Vercel)    │                  │   (Render)    │               │  (Neon)      │
└─────────────┘                  └──────┬───────┘               └─────────────┘
                                          │
                              ┌───────────┴────────────┐
                              ▼                         ▼
                     ┌─────────────────┐      ┌──────────────────────┐
                     │  Claude API      │      │  External ATS APIs   │
                     │  (extraction,    │      │  (Greenhouse, Lever,  │
                     │  explanations)   │      │  Ashby, + a custom    │
                     └─────────────────┘      │  Avular parser)       │
                                                └──────────────────────┘
```

- **Frontend**: `frontend/` — React + Vite, deployed to Vercel, custom domain `launchino.com`.
- **Backend**: `api/` — FastAPI, deployed to Render (Starter tier, always-on), custom domain `api.launchino.com`.
- **Database**: Neon-hosted Postgres, reached via `DATABASE_URL` (no local/dev database — Neon is used for both dev and production, same instance shared with care).
- **Core matching/domain logic**: `src/` — a separate package from `api/`, deliberately kept framework-agnostic (no FastAPI imports), containing the matching engine, ingestion pipeline, and dedup/merge logic. `api/` is a thin HTTP layer on top of `src/`.
- **AI**: Anthropic Claude API, called only from `api/ai_client.py` and `api/extraction_service.py`/`api/explanation_service.py` — never called directly from `src/`.

---

## 3. Repository structure

```
/
├── src/                  # Core domain logic — framework-agnostic, no HTTP/DB
│   ├── schemas.py               # Pydantic models: Talent, ElementValueState, etc.
│   ├── match_engine.py          # Deterministic scoring — FROZEN since v1.2.1
│   ├── activation.py            # Which Fit Dictionary elements are active per profile
│   ├── ordinal_comparators.py / practical_comparators.py
│   ├── candidate_extraction.py / vacancy_extraction.py  # Extraction result contracts
│   ├── canonical_vacancy.py     # Builds CanonicalVacancyProfile from raw sources
│   ├── company_intake.py        # Company-direct vacancy submission path — see §8, does NOT go through dedup/lifecycle
│   ├── vacancy_dedup.py         # Tri-state duplicate detection (duplicate/not/review_required)
│   ├── vacancy_merge.py         # Trust-ranked field-level conflict resolution
│   ├── vacancy_lifecycle.py     # draft/active/updated/stale/closed/archived state machine
│   ├── vacancy_ingestion.py     # Orchestrates dedup+merge+lifecycle for one ingested (scraped) record
│   ├── source_policy.py         # Fail-closed source approval gate
│   ├── source_classification.py / source_schemas.py
│   ├── ind_sponsor_registry.py  # IND sponsor fuzzy-match — built but NOT wired to real data (see §15)
│   ├── job_sources/              # greenhouse.py, lever.py, ashby.py, jsonld.py, avular.py, http_client.py
│   ├── job_discovery_access.py  # Subscription entitlement service (cost-gate for AI matching)
│   ├── job_discovery_pipeline.py # Orchestrates matching+explanation for subscribed candidates only
│   ├── job_recommendations.py   # Recommendation-building support logic used by the pipeline above
│   ├── database_schema.sql      # Full schema (source of truth — see §6)
│   └── ...  (also company_registry.py, dictionary_tools.py, normalisation_registry.py, polling.py,
│              public_weighting.py, survey_contracts.py, vacancy_utils.py — smaller support modules)
├── api/                  # HTTP layer — FastAPI, DB access, Claude API calls
│   ├── main.py                   # App entrypoint, router registration, bootstrap()
│   ├── config.py                  # Env var loading — all secrets fail loudly if missing
│   ├── auth.py                    # JWT issuance/validation, role/ownership checks
│   ├── database.py                # Connection handling, schema bootstrap, seeding
│   ├── rate_limit.py               # slowapi Limiter, proxy-aware IP key
│   ├── ai_client.py                # MODEL_FOR_TASK map, call_claude_structured/text, usage logging
│   ├── comparators_dispatch.py     # Routes each Fit Dictionary element to its src/ comparator function —
│   │                                # an API-layer file added when this HTTP layer was built, NOT part of
│   │                                # the frozen v1.2.1 src/ package (see §5's correction)
│   ├── extraction_service.py       # CV/vacancy extraction orchestration (prompts P01/P04)
│   ├── explanation_service.py      # Match explanation generation (prompt P08)
│   ├── matching_service.py         # persist_match_run, run_match, get_vacancy
│   ├── vacancy_store.py            # CanonicalVacancyProfile ↔ DB row mapping
│   ├── ingestion_store.py          # Persistence for source/company/snapshot/provenance tables
│   ├── job_discovery_scheduler.py  # Manual-trigger-only poll cycle runner
│   ├── job_discovery_runner.py     # Manual-trigger-only real recommendation pipeline runner
│   ├── admin_reports.py / admin_review.py  # Dashboard aggregation + review-queue logic
│   ├── ai_usage.py                 # log_ai_usage() — cost/token logging, never blocks the AI call
│   └── routers/                    # candidates.py, vacancies.py, matches.py, admin.py, admin_reports.py, admin_review.py
├── frontend/              # React + Vite SPA
│   ├── src/pages/          # LoginPage, CandidateSurveyPage, VacancyWorkshopPage, MatchPage, AdminDashboardPage,
│   │                        # PrivacyPolicyPage, TermsOfServicePage
│   ├── src/components/     # TriStateAnswer, ordinal range controls, value-editor registry
│   └── vercel.json          # SPA rewrite rule (required for client-side routing to work)
├── data/                  # Registries and reference data
│   ├── fit_dictionary_starter.json   # The 41 Fit Dictionary elements (5 seeded categories — see §4), canonical schemas
│   ├── source_registry.json          # Fail-closed source approval registry
│   ├── company_registry_live.json    # Real companies being polled (editable, no code change needed)
│   └── mapping_memory.json
├── prompts/                # P01–P21 prompt templates (extraction, explanations, classification)
├── migrations/              # Numbered SQL migrations applied to live Neon on top of the base schema
├── tests/ + api/tests/       # pytest — single `pytest` command runs both (fixed; previously required two commands)
└── PROJECT_NOTES.md          # Running log of deliberate decisions, known limitations, deferred work
```

**Read `PROJECT_NOTES.md` first, always.** It's a standing instruction in this project that any new work session starts by reading this file — it contains reasoning for non-obvious decisions that isn't duplicated here.

---

## 4. The Fit Dictionary — core domain model

The Fit Dictionary (`data/fit_dictionary_starter.json`) defines 41 elements across **5 seeded** categories: **PRACT** (practical: location, sponsorship, contract, work-mode, language — 6 elements), **TEAM** (teamwork style — 7), **CAREER** (career direction — 7), **MOT** (motivation — 12), **ENV** (work environment — 9).

**CAP** (capabilities/skills) and **TASK** (task history) are two further categories that exist conceptually and in the schema (`fit_element_proposal`/`fit_element_alias` tables support a dynamic, per-vacancy proposal-and-alias governance workflow for them), but **have zero seeded elements today and zero application-code references anywhere** — this mechanism is designed but entirely unwired, not just "not yet populated." See §15.

Because these categories have zero real elements, the two *real* default weight profiles (§8 — `src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS` for scraped/ingested vacancies, `frontend/.../VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS` for company-direct submissions without custom weights) weight `CAP`/`TASK` at `0` and split the remaining 100% equally across the 5 real categories (20% each). A real correctness bug where a nonzero weight on a data-less category was being silently renormalized away rather than scored was found and fixed 2026-07-27; see §5 and §15's resolved-defect entry, and `PROJECT_NOTES.md` for the full writeup (including a same-day correction about which file actually mattered — `data/public_weight_profile.json` turned out to be dead code, never read by any real path).

Each (seeded) element has:
- A **comparator key** determining how it's scored (e.g. `ordinal_range`, `ordinal_requirement`, exact-match, semantic-overlap)
- A **candidate_value_schema** and **vacancy_value_schema** — the exact JSON shape a value must take (this is the schema the AI extraction service embeds into its prompts — see §7)
- **Activation conditions** — some elements only become "active" for a given profile based on earlier answers (e.g. sponsorship questions only activate if relevant)

**Tri-state value model** — this is the single most important design principle in the whole system: every element is either `answered` (with a real value), `unknown` (nobody said, don't guess), or `not_applicable`. The matching engine and every AI prompt are built around never collapsing "unknown" into a negative or default value.

---

## 5. Matching engine

`src/match_engine.py`, `src/activation.py`, `src/ordinal_comparators.py`, `src/practical_comparators.py` — **these four files have been frozen and byte-for-byte unchanged since v1.2.1**, through every subsequent feature (job discovery, subscriptions, auth, dashboard). This was a deliberate, repeatedly-verified boundary — every prompt given to Claude Code for new features explicitly excluded these files. (`api/comparators_dispatch.py` performs a related role — routing each element to the right comparator — but it lives in `api/`, not `src/`, and was added when the HTTP layer itself was built, after v1.2.1; it is not part of this frozen set, though it too has been stable since it was introduced.)

**Scoring logic**: for each active element, both sides' values are compared via the relevant comparator, producing an alignment result. Category scores are weighted averages. **Coverage** (what fraction of active elements were actually answered, weighted by importance) gates the final lane: below a 70% coverage threshold, the result is `clarification_required` rather than a confident score — the system deliberately refuses to overclaim confidence on sparse data. This has been verified against real, sparse, real-world data (e.g., a real ingested vacancy with only 2 of 41 elements answered correctly produced `clarification_required`, not a falsely precise number).

**A category with configured weight but zero real elements (CAP/TASK today — see §4) is a case `aggregate_match()` itself doesn't handle specially**: it silently excludes that category's weight from the denominator and renormalizes the overall score over whatever categories *did* have data, with no error and no `clarification_flags` entry (found and fixed 2026-07-27 as a real correctness bug, not just a doc gap — see `PROJECT_NOTES.md`). Rather than touch this frozen function, the fix lives one layer up: `api/matching_service.py`'s `_flag_categories_with_no_data()` runs immediately after every `aggregate_match()` call (both real call sites — `matching_service.run_match` and `api/job_discovery_runner.py`'s deterministic matcher), detects any category where `category_weight > 0 and active_item_count == 0`, and folds a `"{CATEGORY}: no data available for this category"` entry into the *existing* `clarification_flags` mechanism — then recomputes `lane`/`provisional` by calling this file's own unmodified `_assign_lane()` with the updated flags. `match_engine.py` itself was not modified; the safety net is purely additive, downstream, and non-frozen.

---

## 6. Database schema (key tables)

Full source of truth: `src/database_schema.sql` + numbered files in `migrations/`.

| Table | Purpose |
|---|---|
| `fit_element` | The Fit Dictionary itself — the 41 seeded elements' definitions, schemas, comparator keys, activation policies. Everything else in the matching system reads from this table. |
| `fit_element_alias` / `fit_element_proposal` | Schema-only governance mechanism for dynamic, vacancy-specific CAP/TASK elements — **confirmed zero application-code references anywhere**; fully unwired (see §4, §15). |
| `talent` | Candidates. Includes auth fields (`password_hash`), subscription fields (`job_discovery_subscription`, `subscription_expires_at`, `subscription_source`, `job_discovery_campaign_opt_in`), `last_login_at`, `consent_at`/`consent_version`. |
| `company` | Companies. `contact_email` + `password_hash` for auth. |
| `talent_element_value` / `vacancy_element_value` | The actual Fit Dictionary answers. `vacancy_element_value` has `verification_status` (trust tier: `auto_extracted` < `source_verified` < `company_validated`) — `talent_element_value` deliberately has **no** such column (a candidate has one source: themselves; no multi-source conflict to referee). |
| `talent_evidence` | Candidate free-text supporting evidence; hard-deleted (not anonymized) on a GDPR deletion request. |
| `vacancy` | Canonical vacancy profiles — `verification_status`, `lifecycle_status`, `weighting_mode`, `canonical_key`, `content_hash`, timestamps. |
| `vacancy_source_link` | Links a canonical vacancy to the raw source snapshot(s) that produced/updated it — what dedup-review resolution updates when linking a new incoming snapshot to an existing vacancy. |
| `match_run` / `match_item_result` / `match_summary` | Match results: one `match_run` per match request, one `match_item_result` row per scored element, one `match_summary` row per candidate in the run. |
| `job_recommendation` | Job-discovery recommendation records (denormalised score/coverage/lane). Includes the persisted AI explanation text and links to `ai_usage_log` for cost attribution. |
| `job_discovery_batch_run` / `preliminary_opportunity_signal` | Backing tables for §9's three job-discovery cycles — batch-run metrics, and the deterministic-only preliminary-campaign teaser signal for non-subscribers. |
| `human_review` | Designed to record a human override decision on match bridgeability (`match_run_id`, `reviewer_id`, `decision`, `rationale`). **Confirmed zero INSERT statements anywhere in current code — fully unimplemented**, not just under-used (see §15). |
| `company_job_source` / `source_snapshot` / `source_policy` | Ingestion registry, per-poll raw snapshots, and the fail-closed source-approval gate (`enabled` can only be `true` if `terms_review_status='approved'` — enforced by a DB-level `CHECK` constraint, not just application code). |
| `vacancy_field_provenance` / `vacancy_source_conflict` | Field-level "which source said what" and how conflicts were resolved (by trust ranking). |
| `vacancy_dedup_review` | The actionable duplicate-review queue — unique on `(incoming_snapshot_id, candidate_vacancy_id)` with `ON CONFLICT DO NOTHING`, so re-detecting the same ambiguity on a later poll doesn't create duplicate review rows. |
| `poll_run` | Per-source ingestion health history (existed in schema from the start but was unwired until the admin dashboard work — now correctly populated every poll cycle). |
| `ai_usage_log` | Every real Claude API call — task, model, tokens, computed cost, success/failure, attributed to a `talent_id`/`vacancy_id` where applicable. Powers the admin cost dashboard. Error messages are sanitized (type/category only, never raw exception text that could echo submitted content). |
| `model_pricing` | Per-model $/MTok rates, seeded from real published Anthropic pricing. **The Sonnet 5 introductory rate expires 2026-08-31 — needs a manual `UPDATE`, not a code change, after that date.** |

---

## 7. AI extraction system

**`api/ai_client.py`**: the single choke point for all real Claude API calls.
- `MODEL_FOR_TASK` — a named constant mapping task → model: **Sonnet** for CV extraction, vacancy extraction, match explanations (real judgment required); **Haiku** for gap-question generation, source classification, review-flagging (narrow, low-ambiguity tasks).
- `call_claude_structured()` — forces a tool call shaped by the target Pydantic model's JSON schema, then validates the result for real.
- `call_claude_text()` — plain prose generation (used for match explanations).
- `max_tokens=16000` (raised from an original 8192 after real truncation was found silently producing empty-but-schema-valid results — see the truncation bug below). **A truncated response now hard-raises `AIExtractionError` rather than ever silently passing as valid.**
- Every call — success or failure — logs a row to `ai_usage_log` via `log_ai_usage()`, which never lets a logging failure break the underlying AI call. On a schema-validation or API-call failure, the logged `error_message` is sanitized (`_sanitize_error_for_logging()`) to error type/category only — never the raw exception text, which for a Pydantic `ValidationError` would otherwise embed the actual offending submitted value.

**`api/extraction_service.py`**: builds the actual prompts (P01 = CV extraction, P04 = vacancy extraction), embedding each Fit Dictionary element's **real value schema** (not just its label) — this was the root-cause fix for extraction returning wrong key names (see below). `cv_text`/`description_text` inputs are capped at 20,000 characters at the API boundary (`api/models_api.py`) — direct cost control against oversized submissions.

**Two significant bugs found and fixed via real (non-mocked) API trials — worth knowing if extraction ever seems to misbehave again:**
1. **Invented element IDs**: early on, CV extraction invented plausible-but-fake element IDs (e.g. `CAP-SQL`) instead of returning genuinely unmapped terms, because the result schema had no field to put "real skill, no dictionary match" — adding `unmapped_terms: List[str]` fixed the actual cause, not just the prompt wording.
2. **Wrong canonical key names + silent truncation**: extraction reliably got the right *content* but wrong *key names* for several schemas (e.g. `{"sponsorship_required": ...}` instead of the real `{"requirement": ...}`), because the prompt only sent element labels, never the real schema. Separately, the fix that embedded richer schemas pushed some real responses past the `max_tokens` cap, which could produce a schema-valid **but empty** result with zero error signal — the most dangerous class of bug in this system, since it looks like success. Both are fixed and re-verified across multiple comparator families (`ordinal_range`, `ordinal_requirement`) with multiple real trials each, not single lucky passes.

---

## 8. Job discovery / ingestion pipeline

**Two separate vacancy-intake paths exist — this matters, since only one goes through dedup:**
1. **Scraped/ingested** (`src/vacancy_ingestion.py`, described below) — full dedup + merge + lifecycle orchestration.
2. **Company-direct submission** (`src/company_intake.py`'s `canonicalise_company_submission()`, called by `POST /vacancies`) — builds a `CanonicalVacancyProfile` directly from a company's own form submission and inserts it. **This path does not call `vacancy_ingestion.py` at all — no dedup check, no lifecycle state machine.** A company posting what's effectively a duplicate of their own scraped/ingested vacancy today creates a separate row, not a merge.

**Source policy (`src/source_policy.py` + `data/source_registry.json`)**: fail-closed by design. A source can only be used if `terms_review_status == 'approved'` **and** `enabled == true` — enforced twice (application code + a DB `CHECK` constraint), so a misconfiguration at either layer alone can't accidentally enable a non-approved source. LinkedIn/Indeed are hard-coded `prohibited`. Approved sources in the registry today: `greenhouse_public_api`, `lever_public_api`, `ashby_public_api`, `company_page_jsonld`, and `avular_careers_html` (a hand-built, one-off parser for Avular's custom career page — approved only after checking `robots.txt` and their actual Terms & Conditions, not just added by default). Note `lever_public_api` and `company_page_jsonld` are approved but have no real company currently using them in `data/company_registry_live.json`.

**Pipeline flow, scraped path only** (`src/vacancy_ingestion.py`): raw fetch (`src/job_sources/*.py`) → `canonical_vacancy.py` builds a `CanonicalVacancyProfile` → `vacancy_dedup.py` decides `duplicate` / `not_duplicate` / `review_required` (never a forced binary choice) → `vacancy_merge.py` resolves any field conflicts by trust ranking (a company's own direct submission always outranks anything scraped) → `vacancy_lifecycle.py` updates state (`draft/active/updated/stale/closed/archived` — a `closed` vacancy correctly **reopens** if seen again, `archived` never auto-reopens).

**Scheduler (`api/job_discovery_scheduler.py`)**: deliberately **manual-trigger-only** — nothing in `main.py`'s startup, no cron, no background task. This was an explicit product decision (not a missing feature) to avoid unattended polling of real companies' APIs before the operator is ready. Turning on continuous polling later is a small, deliberate config change, not a rebuild.

**Real validated sources as of this document**: Sendcloud (Greenhouse), Axelera AI (Ashby), Monumental (Ashby), Avular (custom parser). Beyond Sports (Ashby) validates but is currently empty (0 open roles) — correctly excluded from ingestion, not silently treated as active.

**Default weighting**: two real, separately-maintained locations, kept in sync by hand (no runtime single-sourcing between a Python backend constant and a bundled frontend constant):
- **`src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS`** — the actual fallback used by every scraped/ingested vacancy (`src/vacancy_ingestion.py` never passes `category_weights` to `canonicalise_raw_vacancy()`, so this constant is always what's used) — `weighting_mode='balanced_default'` until a company confirms its own.
- **`frontend/src/pages/VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS`** — sent by the company-direct-submission form whenever a company doesn't customize weights.

Both are `{PRACT: 20, TEAM: 20, CAREER: 20, MOT: 20, ENV: 20, CAP: 0, TASK: 0}` as of 2026-07-27 — equal weighting across the 5 categories with real seeded elements, `CAP`/`TASK` at exactly `0` (not a nonzero weight against no data). This followed a same-day correction: `data/public_weight_profile.json` (loaded by `src/public_weighting.py`) looks like it should be this default but is **dead code** — confirmed via `grep -rln "load_public_weight_profile"`, referenced only by its own definition and its own test, never by real application code. It's kept content-correct and explicitly marked unused in the file itself, in case something eventually wires it in for real. See `PROJECT_NOTES.md` for the full history, including the original (wrong) claim that this file was the fix.

Companies who want their own weighting can still set `category_weights` explicitly on vacancy creation — this default only applies when nothing custom is specified, and that mechanism was not changed.

---

## 9. Subscription gating (Job Discovery paid tier)

**Design principle**: filter *who enters the pipeline*, not what's shown afterward — a non-subscribed candidate should never trigger a matcher call or an AI explanation call, not just have the result hidden from them.

- **`src/job_discovery_access.py`**: `JobDiscoveryEntitlementService` — the single source of truth for "is this candidate currently entitled to Job Discovery." Handles the case of `active` with no expiry date (valid — manual MVP toggle) vs. a past expiry date (always blocks, even if the status field wasn't updated).
- **`src/job_discovery_pipeline.py`**: three cycles — `run_full_job_discovery_cycle` (full paid matching, entitlement checked **twice**: once at candidate selection, once again immediately before each AI call, to handle expiry mid-batch-run); `run_preliminary_campaign_cycle` (a deterministic-only, opt-in "preliminary campaign" for non-subscribers — no AI, never reveals which vacancy or score, just a teaser count); and `run_subscription_backfill` (a capped backfill for new/renewed subscribers — recent-vacancy scan, capped AI-explanation count). `src/job_recommendations.py` provides supporting recommendation-building logic used by this pipeline.
- Proven via a real end-to-end test with a real active-subscriber candidate (real recommendations, real persisted AI explanations) and a real none-subscriber candidate (zero matcher calls, zero AI calls — asserted directly in a test, not just "no output produced").
- **Admin toggle**: `PATCH /candidates/{id}/subscription` — currently the only way subscriptions change (no Stripe/billing yet, deliberately deferred until after closed-beta customer validation).

---

## 10. Authentication

JWT (PyJWT) + bcrypt password hashing. Three roles: `candidate` (subject = `talent_id`), `company` (subject = `company_id`), `admin` (single identity from env vars `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` — no admin table, deliberately not a full admin-management system). Token expiry: 24h candidate/company, 4h admin (shorter blast radius for the more powerful role). No refresh-token flow — expired token requires re-login (a disclosed, accepted MVP limitation).

**Ownership enforcement**: `company_id` on a new vacancy is always derived from the auth token, never trusted from the request body — closes a real spoofing vector. A candidate can only access their own record/survey/extraction; a company only its own vacancies/matches. Orphaned pre-auth vacancies (`company_id IS NULL`, from before companies had logins) are admin-only editable, never auto-claimable by a newly registered company.

---

## 11. Admin dashboard

Admin-only, built on top of:
- **Cost/usage logging** (`ai_usage_log`, `model_pricing`) — every real AI call attributed to a candidate/vacancy with real, verified-by-hand-calculation cost.
- **Reporting endpoints** (`api/admin_reports.py`): signups over time, active-vs-dormant candidates (30-day window, uses `coalesce()` to correctly handle `NULL` timestamps — a real bug was found and fixed here: naive `NULL >= cutoff` SQL comparisons silently evaluate to `NULL`, not `false`, excluding those rows from both active and dormant buckets), subscription breakdown, per-candidate/company detail reports (coverage %, recommendations, cost), ingestion health.
- **Review queues** (`api/admin_review.py`): duplicate-review (act on real `vacancy_dedup_review` rows, calling the existing unmodified `vacancy_merge.py` logic), sponsor-review (currently always empty — see §15), extraction-review (read-only spot-check view of AI-extracted submissions).

---

## 12. Frontend

React + Vite (`frontend/`). Shared components: a tri-state answer control (answered/unknown/not_applicable, not a binary), ordinal range/slider controls, and a registry of value-editors covering all real comparator-key shapes. Activation logic is **never duplicated in JavaScript** — the frontend calls the backend's real `src/activation.py` logic via a read-only `GET /fit-dictionary` endpoint, so the frontend and matching engine can never silently drift apart.

Candidate survey and vacancy workshop pages both support paste-to-extract (calling the real extraction endpoints) or manual entry, with an editable review screen before confirming — this is the actual mechanism that makes AI extraction trustworthy (a human can see and correct `unmapped_terms` and any AI review flags before anything is saved).

Public, no-auth-required pages also exist: `/privacy` and `/terms`, rendering the Privacy Policy / Terms of Service verbatim from source `.md` files, linked from the registration consent checkbox.

---

## 13. Deployment & infrastructure

| Piece | Where | Notes |
|---|---|---|
| Frontend | Vercel, `launchino.com` + `www.launchino.com` | `vercel.json` has the SPA rewrite rule (required — without it, direct navigation to any client-side route like `/login` 404s). `VITE_API_BASE_URL` is baked in at **build time**, not runtime — changing it requires a redeploy, not just an env var update. |
| Backend | Render (Starter tier, always-on — chosen over Render's free tier specifically to avoid cold-start delays during live demos), `api.launchino.com` | Runs without `--reload` in production. |
| Database | Neon Postgres | Same instance used throughout dev and production — schema/migrations already applied live. |
| Secrets | Render + Vercel environment variable dashboards | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`, JWT signing secret — **all fail loudly if missing**, no hardcoded fallback for any of them (a hardcoded dev-only `DATABASE_URL` fallback was found and deliberately removed for this reason). |
| CORS | Locked to specific real origins | `launchino.com`, `www.launchino.com`, the Vercel/Render platform subdomains, plus `localhost` for continued local dev — not left open. |

---

## 14. Security & compliance

- **Rate limiting** (`slowapi`, keyed on real client IP via `X-Forwarded-For` — required since Render sits in front as a proxy): registration (5/hour), login (10/minute candidate/company, 5/minute admin — the tighter limit for the higher-value single account), and both AI-extraction endpoints (20/hour — real per-call cost).
- **Input validation**: length caps on all public fields, including a 20,000-character cap on CV/vacancy text sent to extraction (direct cost control). A real bug was found and fixed here: `bcrypt` hard-raises on passwords over 72 bytes, and no field previously capped password length — fixed with an explicit `max_length=72`.
- **Error handling**: confirmed (via a real forced unhandled exception, not just code review) that clients only ever see a generic `"Internal Server Error"`, never a stack trace or internal detail.
- **GDPR mechanisms**: `GET /candidates/{id}/export` and `/companies/{id}/export` (full data export, self-or-admin only); `DELETE` endpoints (anonymize identifying fields, delete free-text content, retain anonymized match records since nothing cascades and companies have a legitimate interest in their own hiring history — **this specific approach is a reasonable engineering default, not yet confirmed sufficient for GDPR erasure by a lawyer**); a required consent checkbox + timestamp at registration, enforced both server-side and in the UI.
- **Privacy Policy / Terms of Service**: live at `launchino.com/privacy` and `/terms`, linked from the registration consent checkbox. Rendered verbatim from source `.md` files via `react-markdown` (not retyped) to avoid any accidental wording drift from the approved text.

---

## 15. Known limitations & deliberately deferred work

*(Full detail and reasoning lives in `PROJECT_NOTES.md` — this is a summary.)*

- **Billing (Stripe) is not built.** Deliberately deferred until after closed-beta validation with real customers, so pricing/plans are based on real feedback rather than guesswork. Subscription status is currently set manually via an admin endpoint.
- **CAP/TASK Fit Dictionary categories are unwired.** The 41 seeded elements span only 5 categories (PRACT/TEAM/CAREER/MOT/ENV); CAP and TASK exist conceptually and in the schema (`fit_element_proposal`/`fit_element_alias`), but have zero seeded elements and zero application-code references anywhere. Not a partial implementation — genuinely not started. Both real default weight profiles (§8) correctly weight both at `0` as of 2026-07-27, and any vacancy that still carries a nonzero legacy weight on either gets a clear `clarification_flags` disclosure rather than a silent renormalized score — see the resolved defect below. Building CAP/TASK out for real is still not started.
- **The two real default-weight locations (§8) have no runtime single-sourcing.** `src/canonical_vacancy.py`'s `DEFAULT_PUBLIC_WEIGHTS` and `frontend/.../VacancyWorkshopPage.jsx`'s `DEFAULT_CATEGORY_WEIGHTS` are kept in sync by hand, with comments on each pointing at the other — nothing enforces they stay identical. This already caused one real gap: an earlier fix (2026-07-27) updated only `data/public_weight_profile.json`, which turned out to be dead code that neither location actually reads.
- **RESOLVED 2026-07-27 — CAP/TASK-weighted vacancies previously renormalized silently instead of scoring or erroring.** Found while cross-checking an earlier draft of this document against the real codebase: `aggregate_match()` excluded a zero-data category's weight from the score with no error and no `clarification_flags` entry. Checked directly against the live DB before fixing: 81 of 86 real vacancies carried the old default's `CAP: 30, TASK: 25`, but only 4 real `match_run` rows existed against any of them — all from this project's own test accounts, never a real beta user, and zero `job_recommendation` rows were ever affected. Fixed with `api/matching_service.py`'s `_flag_categories_with_no_data()` (see §5) plus correcting the default profile (see §4, §8). Full detail and the real-data verification: `PROJECT_NOTES.md`.
- **The `human_review` table is fully unimplemented.** Designed to record a human override decision on match bridgeability, but confirmed to have zero INSERT statements anywhere in current code. `assess_bridgeability` in `src/match_engine.py` is intentionally left at `NOT_APPLICABLE`; no bridgeability judgement is auto-generated or ever recorded.
- **Company-direct vacancy submissions bypass dedup/lifecycle entirely.** `src/company_intake.py`'s path (used by `POST /vacancies`) inserts a `CanonicalVacancyProfile` directly, with no call into `vacancy_ingestion.py`'s dedup/merge/lifecycle orchestration — only the scraped/ingested path gets that treatment.
- **IND sponsor-registry is built but not wired to real data.** `src/ind_sponsor_registry.py`'s fuzzy-match logic is real and tested, but only against a test-fixture CSV — it's never been called during real ingestion, and no real, maintained IND dataset has been sourced yet. Wiring the code without real data would be actively misleading (checking real vacancies against fake company names), so this was deliberately left off rather than half-done.
- **No refresh-token flow.** An expired JWT just requires logging in again. Accepted as fine at current scale.
- **The `/workshop` "trust boundary" is only partially closed.** Auth now proves *who* submitted data (a real authenticated company), but nothing enforces that a human actually reviewed an AI-extracted draft before confirming it — the extraction-review dashboard view makes this spot-checkable, but doesn't prevent a technically-possible "confirm without looking" click. Revisit if a stronger guarantee is ever needed (e.g. a signed token issued only by a genuine extraction response).
- **No automatic data-retention enforcement.** Retention *periods* are documented (12-month inactivity flag, 18-month anonymization, 30-day post-deletion backup purge) but nothing currently runs on a schedule to enforce them — manual/future work.
- **Four open legal/compliance questions are explicitly unresolved**, documented in the internal compliance notes (not the public-facing privacy policy): (1) whether the anonymize-plus-retain-match-record deletion approach actually satisfies GDPR erasure obligations, (2) final retention periods, (3) formal legal review of the privacy policy/ToS text itself, (4) whether Launchino's matching functionality falls under the EU AI Act's high-risk recruitment-AI category. **All four require actual legal counsel before scaling beyond a small closed beta** — the current privacy policy and terms of service are a good-faith, product-accurate first draft, not a substitute for that review.
- **Test suite note**: a single bare `pytest` command now correctly runs both `tests/` (core package) and `api/tests/` together (fixed after a period where this required two separate commands — worth knowing if an old report ever seems to cite a suspiciously different total test count).

---

## 16. If something breaks — where to look first

| Symptom | Likely place to look |
|---|---|
| A match result looks wrong | Check `match_engine.py`/`activation.py` inputs first — these files are frozen and well-tested, so a wrong result is almost always bad/missing input data (check `vacancy_element_value`/`talent_element_value`), not the scoring logic itself |
| AI extraction returns odd/wrong data | Check `api/extraction_service.py`'s prompt construction and whether the relevant element's schema is being embedded correctly — this exact class of bug has happened twice before |
| A vacancy seems duplicated or wrongly merged | `src/vacancy_dedup.py` (matching logic) / `src/vacancy_merge.py` (trust-ranked conflict resolution) — check `vacancy_source_conflict` and `vacancy_field_provenance` for the actual resolution trail. Remember: this only applies to the scraped-ingestion path — a company-direct submission (`src/company_intake.py`) never goes through dedup at all (see §8, §15) |
| Ingestion isn't picking up a company | Check `data/source_registry.json` for that source's `terms_review_status`/`enabled`, and `data/company_registry_live.json` for the board token |
| A cost figure looks wrong | Check `model_pricing` is current (the Sonnet 5 rate expires 2026-08-31) and `ai_usage_log` for the actual logged call |
| Someone can't log in / access something they should | `api/auth.py` for role/ownership logic — remember `company_id` is always derived from the token, never the request body |
| Deployment/CORS issue | Remember `VITE_API_BASE_URL` is baked in at frontend build time — a redeploy is required after changing it, not just an env var update |

---

*This document reflects the system as built and verified through real end-to-end testing at each stage, not aspirational design. Where something is described as "deferred" or "not yet wired," that reflects a deliberate decision recorded in `PROJECT_NOTES.md`, not an oversight.*

*Cross-checked against the live codebase on 2026-07-27: file/function/table names, the "frozen since v1.2.1" boundary, §15's limitations list, and §3's repo structure were verified directly (not from memory) before this document was saved. See the corrections list delivered alongside this file for exactly what changed from the original draft.*
