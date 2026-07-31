from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from api import REPO_ROOT
from api.config import DATABASE_URL

SCHEMA_PATH = REPO_ROOT / "src" / "database_schema.sql"
FIT_DICTIONARY_PATH = REPO_ROOT / "data" / "fit_dictionary_starter.json"

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def get_connection() -> Iterator[Connection]:
    """FastAPI dependency: one transactional connection per request."""
    with engine.begin() as conn:
        yield conn


def _schema_present(conn: Connection) -> bool:
    row = conn.execute(
        text(
            "select 1 from information_schema.tables "
            "where table_schema = 'public' and table_name = 'fit_element'"
        )
    ).first()
    return row is not None


def init_schema() -> None:
    """Apply src/database_schema.sql if the schema has not been created yet.

    The schema file itself is the single source of truth for table shape and
    constraints; this only decides whether it still needs to run.
    """
    with engine.connect() as conn:
        if _schema_present(conn):
            return
    raw_conn = engine.raw_connection()
    try:
        script = SCHEMA_PATH.read_text(encoding="utf-8")
        cursor = raw_conn.cursor()
        cursor.execute(script)
        cursor.close()
        raw_conn.commit()
    finally:
        raw_conn.close()


def _is_schema_change_additive_only(old_schema: Any, new_schema: Any) -> bool:
    """True if new_schema only adds new keys/items relative to old_schema --
    never removes an existing key, renames one (indistinguishable from
    remove+add at this structural level), or changes an existing key's
    type/shape. Recurses into nested dicts and into the single template
    object inside a schema's example arrays (e.g. "jobs": [{...}]).

    Deliberately conservative: any change to a leaf value (a type-
    description string like "string|null") counts as incompatible even if
    it looks like a harmless narrowing/widening -- this function only has
    to say yes to the genuinely safe case (add a new optional field), not
    every case that might turn out fine in practice.
    """
    if isinstance(old_schema, dict):
        if not isinstance(new_schema, dict):
            return False  # whole shape changed from object to something else
        return all(
            key in new_schema and _is_schema_change_additive_only(old_value, new_schema[key])
            for key, old_value in old_schema.items()
        )  # extra keys in new_schema are fine
    if isinstance(old_schema, list):
        if not isinstance(new_schema, list):
            return False
        if not old_schema or not new_schema:
            return True  # nothing concrete to compare (e.g. a [] placeholder)
        return _is_schema_change_additive_only(old_schema[0], new_schema[0])
    return old_schema == new_schema  # leaf value: must be byte-for-byte unchanged


def _element_has_existing_candidate_data(conn: Connection, element_id: str) -> bool:
    return conn.execute(
        text("select 1 from talent_element_value where element_id = :element_id limit 1"),
        {"element_id": element_id},
    ).first() is not None


def _element_has_existing_vacancy_data(conn: Connection, element_id: str) -> bool:
    return conn.execute(
        text("select 1 from vacancy_element_value where element_id = :element_id limit 1"),
        {"element_id": element_id},
    ).first() is not None


def seed_fit_dictionary(
    *, elements: Optional[list] = None, force_element_ids: frozenset = frozenset(),
) -> dict:
    """Load the universal Fit Dictionary starter set into fit_element (idempotent).

    Safety check (added after a real question about this function's blast
    radius -- see PROJECT_NOTES.md): before upserting an element that
    already has real answered data (talent_element_value /
    vacancy_element_value rows), this compares its incoming
    candidate_value_schema/vacancy_value_schema against what's currently
    stored for that element_id. A purely additive change (new optional
    keys only) still applies automatically, exactly as before this check
    existed. A change that renames, removes, or changes the type of an
    existing key is refused -- that element's row is left completely
    untouched, a warning is printed, and it's reported in the returned
    "skipped" list -- unless its element_id is explicitly passed in
    force_element_ids, an intentional override for when the incompatibility
    has already been handled (e.g. via a real migration of existing rows).

    This only guards candidate_value_schema/vacancy_value_schema -- a
    comparator_key or category change isn't covered by this check and
    still applies unconditionally, same as before.

    elements defaults to reading data/fit_dictionary_starter.json; a test
    can pass a synthetic list directly instead, since this file is fixed
    and can't itself represent a "before vs. after" schema edit.
    """
    if elements is None:
        elements = json.loads(FIT_DICTIONARY_PATH.read_text(encoding="utf-8"))
    seeded = 0
    skipped: list[dict] = []
    with engine.begin() as conn:
        for element in elements:
            element_id = element["element_id"]
            current = conn.execute(
                text(
                    "select candidate_value_schema, vacancy_value_schema from fit_element "
                    "where element_id = :element_id"
                ),
                {"element_id": element_id},
            ).mappings().first()

            if current is not None and element_id not in force_element_ids:
                incompatible_field = None
                if (
                    not _is_schema_change_additive_only(current["candidate_value_schema"], element["candidate_value_schema"])
                    and _element_has_existing_candidate_data(conn, element_id)
                ):
                    incompatible_field = "candidate_value_schema"
                elif (
                    not _is_schema_change_additive_only(current["vacancy_value_schema"], element["vacancy_value_schema"])
                    and _element_has_existing_vacancy_data(conn, element_id)
                ):
                    incompatible_field = "vacancy_value_schema"
                if incompatible_field:
                    print(
                        f"seed_fit_dictionary WARNING: skipped {element_id!r} -- {incompatible_field} changed in a "
                        "way that isn't purely additive (a key was renamed, removed, or changed type), and real "
                        "answered rows already exist for it. Not auto-applying -- resolve with a real migration of "
                        "the existing rows, then re-run with this element_id in FIT_DICTIONARY_FORCE_SCHEMA_CHANGES "
                        "to confirm the override.",
                        flush=True,
                    )
                    skipped.append({"element_id": element_id, "field": incompatible_field})
                    continue

            conn.execute(
                text(
                    """
                    insert into fit_element (
                        element_id, category, label, definition, activation_policy,
                        candidate_question, vacancy_question, candidate_value_schema,
                        vacancy_value_schema, evidence_rule, comparator_key,
                        sharing_status, is_template, version, active
                    ) values (
                        :element_id, :category, :label, :definition, :activation_policy,
                        :candidate_question, :vacancy_question, cast(:candidate_value_schema as jsonb),
                        cast(:vacancy_value_schema as jsonb), :evidence_rule, :comparator_key,
                        :sharing_status, :is_template, :version, :active
                    )
                    on conflict (element_id) do update set
                        category = excluded.category,
                        label = excluded.label,
                        definition = excluded.definition,
                        activation_policy = excluded.activation_policy,
                        candidate_question = excluded.candidate_question,
                        vacancy_question = excluded.vacancy_question,
                        candidate_value_schema = excluded.candidate_value_schema,
                        vacancy_value_schema = excluded.vacancy_value_schema,
                        evidence_rule = excluded.evidence_rule,
                        comparator_key = excluded.comparator_key,
                        sharing_status = excluded.sharing_status,
                        is_template = excluded.is_template,
                        version = excluded.version,
                        active = excluded.active,
                        updated_at = now()
                    """
                ),
                {
                    "element_id": element["element_id"],
                    "category": element["category"],
                    "label": element["label"],
                    "definition": element["definition"],
                    "activation_policy": element["activation_policy"],
                    "candidate_question": element["candidate_question"],
                    "vacancy_question": element["vacancy_question"],
                    "candidate_value_schema": json.dumps(element["candidate_value_schema"]),
                    "vacancy_value_schema": json.dumps(element["vacancy_value_schema"]),
                    "evidence_rule": element["evidence_rule"],
                    "comparator_key": element["comparator_key"],
                    "sharing_status": element["sharing_status"],
                    "is_template": element.get("is_template", False),
                    "version": element.get("version", "1.2.1"),
                    "active": element.get("active", True),
                },
            )
            seeded += 1
    return {"seeded_count": seeded, "skipped": skipped}


def seed_model_pricing() -> int:
    """Seed model_pricing from api/ai_usage.py's DEFAULT_MODEL_PRICING (idempotent).

    Insert-if-missing, never overwrite: an admin who later updates a price
    directly in this table (manually, or via a future admin UI) must have that
    change survive the next restart, not get silently clobbered by this seed --
    that is the whole point of the "update later without a code change" table.

    Imports api.ai_usage lazily to avoid a circular import (api.ai_usage
    imports api.database.engine for its own logging inserts).
    """
    from api.ai_usage import DEFAULT_MODEL_PRICING

    with engine.begin() as conn:
        for model, prices in DEFAULT_MODEL_PRICING.items():
            conn.execute(
                text(
                    """
                    insert into model_pricing (model, input_price_per_million, output_price_per_million)
                    values (:model, :input_price, :output_price)
                    on conflict (model) do nothing
                    """
                ),
                {
                    "model": model,
                    "input_price": prices["input_per_million"],
                    "output_price": prices["output_per_million"],
                },
            )
    return len(DEFAULT_MODEL_PRICING)


def bootstrap() -> None:
    init_schema()
    # FIT_DICTIONARY_FORCE_SCHEMA_CHANGES: comma-separated element_ids -- the
    # explicit confirmation flag for seed_fit_dictionary's safety check (see
    # its own docstring). Empty/unset means "no overrides", the normal case.
    force_element_ids = frozenset(
        element_id.strip()
        for element_id in os.environ.get("FIT_DICTIONARY_FORCE_SCHEMA_CHANGES", "").split(",")
        if element_id.strip()
    )
    result = seed_fit_dictionary(force_element_ids=force_element_ids)
    if result["skipped"]:
        print(
            f"seed_fit_dictionary: {len(result['skipped'])} element(s) skipped this startup, see warnings above -- "
            f"{[s['element_id'] for s in result['skipped']]}",
            flush=True,
        )
    seed_model_pricing()
