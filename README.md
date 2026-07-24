# SHEXON Talent Fit + Job Discovery reference package — v2.1

This package accompanies **SHEXON Talent Fit + Job Discovery Automation — Implementation Blueprint v2.1**.

It is an implementation-oriented reference for:

- the v1 company-direct Talent Fit flow, where a company pays and may match against the complete eligible talent pool;
- approved-source public-vacancy discovery and canonical ingestion;
- the paid **full Job Discovery** candidate flow;
- a separate, low-cost **preliminary campaign-matching** flow for opted-in non-subscribers;
- subscription expiry, renewal, recommendation visibility and 14-day subscriber backfill.

It is not production legal advice, a finished billing integration, or a licence to access any website.

## Central v2.1 access decision

The deterministic matching engine remains subscription-unaware. Access is controlled in the Job Discovery orchestration boundary.

- **Company-direct matching remains unrestricted by Job Discovery subscription.**
- **Vacancy ingestion remains universal.** A vacancy is fetched, canonicalised and deduplicated once, independent of subscriber count.
- **Full Job Discovery begins only for an effectively active entitlement.** Candidate selection happens before matching and before AI calls.
- `active + subscription_expires_at=NULL` is valid for the initial MVP and remains active until SHEXON changes the status.
- A past expiry blocks access even when the stored status has not yet been updated by billing automation.
- Existing recommendation records are retained internally when access expires, hidden from the candidate, and restored after renewal only when the vacancy remains current and fresh.

## Controlled non-subscriber campaigns

SHEXON may run a separate deterministic-only campaign batch for non-subscribers who have opted in and have a sufficiently complete profile.

This path:

- evaluates only recent, recommendable vacancies;
- creates a lightweight `PreliminaryOpportunitySignal`;
- generates no AI explanation;
- creates no `JobRecommendation`;
- exposes no vacancy details or match score to the candidate;
- supports truthful messaging such as “we identified recent opportunities that may fit your profile”.

After subscription, the system revalidates the vacancy and match before showing details or generating personalised analysis.

## New-subscriber and renewal backfill

The reference policy evaluates vacancies that are:

- `ACTIVE` or `UPDATED`;
- posted, first observed or materially changed within the previous 14 days;
- limited to 50 vacancies per backfill;
- limited to 10 stored recommendations and 5 immediate AI explanations.

Results are ordered by result lane, match score, coverage and then freshness. Freshness is a tie-breaker, not a replacement for fit quality.

## v2.0.1 reliability hardening retained

- CLOSED vacancies reactivate when directly observed again; ARCHIVED remains human-controlled.
- STALE, CLOSED and ARCHIVED vacancies are excluded from recommendations.
- Source access fails closed unless review status is exactly `approved`.
- Duplicate detection establishes company identity before title/location similarity.
- Canonical keys generate indexed candidate sets rather than acting as unique identity proof.
- Fuzzy IND sponsor-name matches remain possible matches requiring human review.

## Package structure

### Talent Fit core

- `data/fit_dictionary_starter.json`
- `data/candidate_survey.json`
- `data/vacancy_workshop.json`
- `src/activation.py`
- `src/ordinal_comparators.py`
- `src/practical_comparators.py`
- `src/match_engine.py`

### Vacancy discovery and lifecycle

- `src/source_policy.py`
- `src/source_classification.py`
- `src/job_sources/`
- `src/canonical_vacancy.py`
- `src/vacancy_ingestion.py`
- `src/vacancy_dedup.py`
- `src/vacancy_lifecycle.py`
- `src/job_recommendations.py`

### v2.1 access and orchestration

- `data/job_discovery_access_config.json` — explicit MVP settings and campaign/backfill limits.
- `src/job_discovery_access.py` — central entitlement, campaign eligibility, freshness and recent-vacancy selection.
- `src/job_discovery_pipeline.py` — full subscriber cycle, deterministic campaign cycle, 14-day backfill and renewal visibility.
- `migrations/003_v2_0_1_to_v2_1_0.sql` — talent entitlement fields, batch metrics, preliminary signals and material-change timestamp.
- `examples/demo_subscription_gate.py` — executable access-flow demonstration.
- `tests/test_job_discovery_access.py`
- `tests/test_job_discovery_pipeline.py`
- `tests/test_v2_1_contracts.py`

### Prompt boundary

Prompts P01–P21 are retained unchanged. The access layer decides whether P08/P19-style candidate explanations may be called; prompt templates do not decide entitlement.

## Quick start

```bash
python -m pip install -r requirements.txt
pytest -q
PYTHONPATH=src python examples/demo_match.py
PYTHONPATH=src python examples/demo_ingestion.py
PYTHONPATH=src python examples/demo_job_recommendations.py
PYTHONPATH=src python examples/demo_subscription_gate.py
```

## Recommended implementation sequence

1. Apply migration `003_v2_0_1_to_v2_1_0.sql`.
2. Add the central entitlement service to the Job Discovery candidate selector.
3. Recheck entitlement immediately before AI explanation generation and recommendation storage.
4. Keep the company-direct repository/query path separate and unfiltered by subscription.
5. Add the preliminary campaign queue with opt-in, thresholds and strict “no explanation/no details” constraints.
6. Add the 14-day backfill trigger for new and renewed subscribers.
7. Add candidate-facing access checks for stored recommendations.
8. Connect billing later by updating the effective entitlement fields; do not pass raw payment-provider state into matching.

## Boundaries

- Subscription logic must not enter `match_engine.py`, comparators, activation or coverage.
- Preliminary signals are not recommendations and must never be presented as a vacancy shortlist.
- A campaign signal must be revalidated after subscription before disclosure.
- No AI explanation is generated for a non-subscriber campaign signal.
- Existing recommendations remain internal while access is inactive.
- Company-direct matching and vacancy ingestion remain unaffected.
- Do not scrape LinkedIn or Indeed directly or bypass access controls.
- Do not auto-apply to vacancies.
