# v2.0.1 patch notes

This maintenance release implements the five reliability findings raised during external QA.

## 1. Vacancy reopening and recommendation eligibility

- `mark_seen()` reactivates a `CLOSED` vacancy when it is directly observed again, even when its canonical content is unchanged.
- `ARCHIVED` remains a deliberate human-controlled state and never reopens automatically.
- Closure and reopening reasons/timestamps are stored.
- Recommendation code explicitly allows only `ACTIVE` and `UPDATED` profiles.

## 2. Fail-closed source governance

- `assert_allowed()` requires `terms_review_status == approved` before any other route check.
- `needs_review`, `partner_only` and `prohibited` remain blocked even if a configuration error sets `enabled=true`.
- PostgreSQL adds `check (not enabled or terms_review_status='approved')` as defence in depth.

## 3. Safer duplicate handling

- Duplicate decisions are tri-state: `duplicate`, `not_duplicate`, `review_required`.
- Company identity is established before title/location comparison.
- Generic title/location similarity cannot merge records from different or unresolved companies.
- Archived possible duplicates enter review as possible reposts.
- Ambiguous pairs are not merged and can be stored in `vacancy_dedup_review`.

## 4. Indexed candidate generation

- The in-memory reference repository indexes source/external IDs, canonical keys, internal company IDs, domains and names.
- Fuzzy comparison runs only on the generated candidate set.
- The PostgreSQL canonical-key index is non-unique because the key is a lookup fingerprint, not definitive identity.

## 5. Conservative sponsor-register matching

- Exact KvK and exact legal-name matches may produce a verified company-level register signal.
- Fuzzy name matches produce `recognised_sponsor=null`, `possible_match=true`, and `human_review_required=true`.
- No company-level register result is treated as proof that a particular vacancy offers sponsorship.
