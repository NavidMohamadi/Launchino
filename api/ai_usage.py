"""Records every real Claude API call into ai_usage_log for admin cost reporting.

Called from api/ai_client.py's call_claude_structured/call_claude_text -- the
only two call sites in the codebase that ever hit the Claude API, so hooking
logging in there covers every task (cv_extraction, vacancy_extraction,
match_explanation, and any future task added to MODEL_FOR_TASK) without
needing to touch each individual caller's business logic.

Logging failures must never break the underlying AI call: a DB hiccup while
writing a usage row should not turn an otherwise-successful extraction into a
500 for the user. See log_ai_usage's try/except.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import text

from api.database import engine

# Real, current per-million-token USD pricing. Source: Anthropic's published
# pricing page (platform.claude.com/docs/en/about-claude/pricing), checked
# 2026-07-24. This dict only seeds model_pricing's initial rows (see
# api/database.py's seed_model_pricing) -- it is never read at request time,
# so updating a price later means editing the model_pricing table directly,
# not this constant or any other code.
#
# claude-sonnet-5 is on introductory pricing ($2/$10 per MTok in/out) through
# 2026-08-31; standard pricing after that is $3/$15. Update the model_pricing
# row directly when that changes -- do not rely on re-running this seed, since
# it deliberately never overwrites an existing row.
DEFAULT_MODEL_PRICING = {
    "claude-sonnet-5": {"input_per_million": Decimal("2.00"), "output_per_million": Decimal("10.00")},
    "claude-haiku-4-5-20251001": {"input_per_million": Decimal("1.00"), "output_per_million": Decimal("5.00")},
}


def log_ai_usage(
    *, task: Optional[str], model: str, input_tokens: int, output_tokens: int, success: bool,
    talent_id: Optional[str] = None, vacancy_id: Optional[str] = None, error_message: Optional[str] = None,
) -> None:
    try:
        with engine.begin() as conn:
            pricing_row = conn.execute(
                text(
                    "select input_price_per_million, output_price_per_million "
                    "from model_pricing where model = :model"
                ),
                {"model": model},
            ).first()
            if pricing_row:
                input_price, output_price = pricing_row
            else:
                # Unknown model (e.g. added to MODEL_FOR_TASK without a matching
                # model_pricing row) -- still log the real usage, just at $0
                # rather than silently dropping the row or crashing the caller.
                input_price, output_price = Decimal("0"), Decimal("0")

            cost = (Decimal(input_tokens) / Decimal(1_000_000) * input_price) + (
                Decimal(output_tokens) / Decimal(1_000_000) * output_price
            )

            conn.execute(
                text(
                    """
                    insert into ai_usage_log (
                        usage_id, task, model, talent_id, vacancy_id,
                        input_tokens, output_tokens, estimated_cost_usd, success, error_message
                    ) values (
                        :usage_id, :task, :model, :talent_id, :vacancy_id,
                        :input_tokens, :output_tokens, :estimated_cost_usd, :success, :error_message
                    )
                    """
                ),
                {
                    "usage_id": str(uuid.uuid4()), "task": task, "model": model,
                    "talent_id": talent_id, "vacancy_id": vacancy_id,
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "estimated_cost_usd": cost, "success": success, "error_message": error_message,
                },
            )
    except Exception as exc:
        # Deliberately broad: any failure here (bad connection, schema drift,
        # whatever) must not propagate into the caller's real AI-call result.
        print(f"[ai_usage_log] failed to record usage (task={task}, model={model}): {exc}")
