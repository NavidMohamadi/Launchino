from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

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


def seed_fit_dictionary() -> int:
    """Load the universal Fit Dictionary starter set into fit_element (idempotent)."""
    elements = json.loads(FIT_DICTIONARY_PATH.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for element in elements:
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
    return len(elements)


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
    seed_fit_dictionary()
    seed_model_pricing()
