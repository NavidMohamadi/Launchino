# SHEXON v2.1 patch notes — Job Discovery access control

## Added

- Effective Job Discovery entitlement fields on `Talent` and the `talent` table.
- `JobDiscoveryEntitlementService` as the single source of truth for active access.
- Active access with no expiry for the manual MVP.
- Expiry-aware access when a timestamp is present.
- Candidate selection before deterministic matching and before AI calls.
- A second entitlement check immediately before explanation generation and recommendation storage.
- Separate preliminary campaign matching for opted-in non-subscribers.
- Lightweight preliminary signals with database constraints preventing AI explanations and candidate-visible vacancy details.
- Retain/hide/restore behavior for historical recommendations.
- Fourteen-day backfill for new or renewed subscribers.
- `last_material_change_at` for reliable recent-vacancy selection.
- Batch metrics separating deterministic comparisons, AI calls, full recommendations and preliminary signals.

## Explicitly unchanged

- Deterministic matching, activation, comparators, coverage and lanes.
- Company-direct candidate matching.
- Vacancy polling, acquisition, canonicalisation, extraction and deduplication.
- Prompts P01–P21.

## MVP commercial decisions implemented

- `active + expires_at=NULL` is permitted.
- Non-subscriber campaigns may use deterministic matching only, under opt-in and batch limits.
- Existing recommendations are retained internally on expiry and hidden from candidate access.
- Renewal restores only still-active, recently observed vacancies.
- New subscribers receive a controlled 14-day vacancy backfill.
