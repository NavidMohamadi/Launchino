# SHEXON Talent Fit MVP — API layer

A FastAPI + PostgreSQL shell around the deterministic matching library in
`src/`. It does not change any scoring, activation, or aggregation logic —
it persists survey answers using the schema in `src/database_schema.sql`,
then hands stored values to the unmodified `src/` functions to run a match.

## Setup

```bash
python -m pip install -r api/requirements.txt
```

Point at a PostgreSQL database (created empty; the app creates its own
tables on first start):

```bash
export DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/shexon_talent_fit"
```

Run the server:

```bash
uvicorn api.main:app --reload
```

On startup the app:
1. Runs `src/database_schema.sql` if `fit_element` does not already exist.
2. Upserts the 41-element universal Fit Dictionary from
   `data/fit_dictionary_starter.json` into the `fit_element` table.

Interactive API docs are then available at `http://localhost:8000/docs`.

## Endpoints

- `POST /candidates` — register a candidate (`full_name`, `email`).
- `POST /candidates/{talent_id}/survey` — submit one or more element values
  (`element_id`, `value`, `value_status`, `source_type`, ...), shaped like a
  row of `talent_element_value`. Each answer is validated with
  `src/schemas.py`'s `TalentElementValue` before being stored as a new
  version (talent answers are versioned; the match always uses the latest).
- `POST /vacancies` — create a vacancy (`company_id`, `role_title`).
- `POST /vacancies/{vacancy_id}/workshop` — submit one or more element values
  shaped like `vacancy_element_value` rows (adds `item_importance`,
  `requirement_type`, `trainability_window`). Validated with
  `VacancyElementValue`; upserted per element (no versioning — one current
  answer per vacancy element).
- `POST /vacancies/{vacancy_id}/match` — run a match: give `talent_ids` and a
  `category_weights` map (must sum to 100, per `MatchConfiguration`). For
  each candidate this loads their latest survey answers and the vacancy's
  workshop answers, resolves activation/value-status with `src/activation.py`,
  scores each answered item with the matching `src/ordinal_comparators.py` /
  `src/practical_comparators.py` / `src/match_engine.py` comparator, and
  aggregates with `src/match_engine.aggregate_match`. Persists a `match_run`,
  one `match_item_result` row per element, and one `match_summary` row per
  candidate.
- `GET /matches/{match_run_id}` — fetch a stored match run and its summaries.

## What this layer adds beyond src/

`comparators_dispatch.py` maps each Fit Dictionary element's
`comparator_key` to the right `src/` comparator function. One key,
`semantic_overlap` (used by the CAREER elements), has no `src/`
implementation — the blueprint treats free-text role-direction matching as
an AI-assisted step (`prompts/P06_item_comparison.txt`). This layer supplies
a deterministic exact-text-overlap placeholder that always flags the item
for clarification, so the endpoint stays usable without wiring an AI call;
swap `score_semantic_overlap` for a real AI-assisted comparison when that
layer exists.

## Known scope limits

- Only the universal Fit Dictionary starter set (PRACT/TEAM/CAREER/MOT/ENV)
  is seeded. Vacancy-specific dynamic `CAP`/`TASK` elements
  (`fit_element_proposal` / alias-approval workflow) are not wired up yet.
- Bridgeability review (`assess_bridgeability` in `src/match_engine.py`) is a
  human-review step and is intentionally left at `NOT_APPLICABLE` here; no
  bridgeability judgement is auto-generated.
- No auth layer — add one before exposing this beyond a trusted network.
