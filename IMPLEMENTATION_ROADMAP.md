# SHEXON v2.1 implementation roadmap

## Phase 0 — preserve existing boundaries

- Freeze `match_engine.py`, comparators, activation and coverage behavior.
- Keep public vacancy ingestion independent of candidates and billing.
- Keep company-direct talent search on its existing unrestricted candidate query.

## Phase 1 — entitlement data and service

- Apply migration 003.
- Backfill all talent records to `job_discovery_subscription='none'`.
- Implement admin controls for manual active/expired state and optional expiry.
- Use `JobDiscoveryEntitlementService` for every full Job Discovery access decision.

## Phase 2 — full paid pipeline gate

- Replace the broad candidate query with the effective-active candidate selector.
- Recheck access immediately before each AI explanation and recommendation write.
- Record included/skipped candidates and AI usage in `job_discovery_batch_run`.
- Confirm zero match runs, AI calls and recommendation writes for ineligible candidates.

## Phase 3 — campaign opportunity detection

- Require campaign opt-in and a complete/ready profile.
- Limit the comparison set to recent active/updated vacancies.
- Store only qualifying preliminary signals.
- Enforce no explanation and no candidate-visible details in code and database constraints.
- Add campaign controls for frequency, thresholds and maximum signals.

## Phase 4 — renewal and subscriber backfill

- Trigger 14-day backfill after new activation or renewal.
- Evaluate at most 50 recent vacancies.
- Store at most 10 recommendations and generate at most 5 immediate AI explanations.
- Order by lane, fit, coverage and freshness.
- Revalidate preliminary signals rather than converting them blindly.

## Phase 5 — candidate access and billing integration

- Block recommendation APIs while entitlement is inactive.
- Retain records internally; restore only fresh/current vacancies after renewal.
- Connect Stripe or another provider by translating provider events into effective entitlement updates.
- Keep raw billing-provider status outside matching and vacancy logic.

## Release gates

- Company-direct tests prove unsubscribed talents remain matchable.
- Vacancy ingestion tests run with zero subscribers.
- Full Job Discovery tests prove inactive talents cause zero matching and AI work.
- Campaign tests prove signals contain no AI output or visible vacancy details.
- Backfill and renewal tests enforce window, caps, ordering and freshness.
- Audit metrics reconcile candidate count, deterministic comparisons, AI calls and stored outputs.
