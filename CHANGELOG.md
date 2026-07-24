# Changelog

## 2.1.0 — 22 July 2026

Job Discovery subscription and campaign access release.

- Add effective Job Discovery entitlement state and optional expiry to talent records; existing and new talents default to `none`.
- Allow active access with no expiry for the manual MVP while treating a past expiry as inactive.
- Filter paid Job Discovery candidates before deterministic matching and before AI explanation generation.
- Keep company-direct matching, vacancy ingestion and the deterministic match engine subscription-unaware.
- Add deterministic-only preliminary campaign signals for opted-in non-subscribers, with no AI explanation, recommendation record or candidate-visible vacancy details.
- Retain historical recommendations internally on expiry, hide them while inactive, and restore only fresh/current records after renewal.
- Add a 14-day new-subscriber/renewal backfill with explicit cost caps and fit-first ordering.
- Add `last_material_change_at`, Job Discovery batch metrics, migration 003 and expanded executable QA.

## 2.0.1 — 22 July 2026

Reliability and trust hardening patch.

- Reopen a CLOSED vacancy when the same job is directly observed again, while keeping ARCHIVED human-controlled.
- Record closure and reopening reasons/timestamps and exclude stale, closed and archived vacancies from recommendations.
- Make source acquisition fail closed unless `terms_review_status` is exactly `approved`; add database defence-in-depth.
- Replace binary duplicate logic with duplicate/not-duplicate/review-required outcomes and require company identity before title/location auto-merge.
- Use source/external ID, canonical key and company indexes to generate duplicate candidates before fuzzy comparison.
- Treat canonical keys as non-unique lookup fingerprints rather than proof of identity.
- Add a duplicate-review queue table and v2.0.1 migration.
- Distinguish exact KvK/legal-name sponsor matches from fuzzy possible matches that require human review.
- Expand executable QA from 50 to 65 tests.

## 2.0.0 — 22 July 2026

Major Job Discovery Automation release.

- Added one Canonical Vacancy Profile for company-direct and public-web vacancies.
- Added source metadata, verification status, field provenance, raw snapshots and source conflicts.
- Added approved public adapters for Greenhouse, Lever, Ashby and company-page JobPosting JSON-LD.
- Added a source policy registry that blocks direct LinkedIn and Indeed scraping and reserves approved partner routes for future use.
- Added company/source registry, polling logic, deduplication, source merge, versioning and vacancy lifecycle.
- Added public-vacancy weighting modes and explicit provisional-match handling.
- Added talent-facing job recommendation ranking.
- Added optional IND recognised-sponsor enrichment as a company signal, never proof of vacancy sponsorship.
- Added canonical vacancy form, source registry, public weight profile, fixtures, migration outline and prompts P15–P21.
- Expanded executable QA from 25 to 50 tests.

## 1.2.1 — 20 July 2026

Maintenance integrity release: `ANSWERED` talent and vacancy element values require a non-empty payload in Pydantic and PostgreSQL; five executable tests cover answered, unknown and not-scored payload states; the blueprint package removes unused hyperlink relationships.

## 1.2 — 20 July 2026

Activation and survey-contract release: element-level activation policies; ANSWERED/UNKNOWN/NOT_SCORED states; in-scope coverage; five-point environment/motivation ranges; reusable twelve-factor vacancy motivation profile; split teamwork activation; schema-enforced CAP/TASK proposals and alias relationships; reviewer checklist and expanded executable QA.

## 1.1 — 20 July 2026

Technical QA release: category-code consistency, operational result lanes, practical comparators, single-source weights, full FitElement schema, dynamic-element governance, separate bridgeability, complete motivation dictionary, corrected tests and references.
