# SHEXON Talent Fit + Job Discovery v2.1 — test report

**Execution date:** 22 July 2026  
**Command:** `pytest -q`  
**Result:** **87 passed, 0 failed**

## Coverage retained from v1.2.1 and v2.0.1

- Fit Dictionary activation policy and schema governance
- ANSWERED / UNKNOWN / NOT_SCORED state integrity
- five-point ordinal ranges and survey contracts
- deterministic category scoring, coverage and result lanes
- dedicated practical comparators
- canonical vacancy form and public adapters
- fail-closed source policy
- company/source classification
- indexed tri-state deduplication and merge behavior
- reversible lifecycle and explicit recommendation eligibility
- public weighting and sponsor registry confidence boundaries
- ingestion idempotency and database patch contracts

## New v2.1 tests

- active entitlement with null expiry is valid
- none, expired and past-expiry states are blocked
- future expiry remains active
- subscription timestamps must be timezone-aware
- campaign eligibility is separate from subscription entitlement
- recent-vacancy selection uses a 14-day window and excludes non-recommendable states
- stored recommendations require current lifecycle and recent observation before restoration
- non-subscribers cause zero full-pipeline matching, AI calls and recommendation records
- active subscribers receive deterministic matches and AI explanations
- entitlement is rechecked before AI generation and recommendation storage
- campaign processing creates lightweight signals only
- campaign thresholds and per-talent caps are enforced
- new-subscriber backfill excludes vacancies older than 14 days
- fit is ranked before freshness
- recommendations are hidden on expiry and restored after renewal
- closed or insufficiently fresh stored vacancies do not restore
- `match_engine.py` contains no subscription or entitlement logic
- database and migration contracts include entitlement, campaign, batch and material-change fields
- prompt files P01–P21 remain present
- package documentation preserves separate full, campaign and company-direct flows

## Executable examples

The following completed successfully:

```text
PYTHONPATH=src python examples/demo_match.py
PYTHONPATH=src python examples/demo_ingestion.py
PYTHONPATH=src python examples/demo_job_recommendations.py
PYTHONPATH=src python examples/demo_subscription_gate.py
```

The subscription demo confirms:

- only the active subscriber enters the full pipeline;
- only the opted-in non-subscriber enters the preliminary campaign path;
- campaign matching generates zero AI explanations and zero recommendations;
- the 14-day backfill excludes the older vacancy;
- stored recommendations are hidden while expired and restored after renewal.
