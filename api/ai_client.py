"""Thin wrapper around the Claude API for structured-extraction and free-text tasks.

Model choice is a single named mapping (MODEL_FOR_TASK) so retuning any one
task later is a one-line edit, not a refactor. cv_extraction, vacancy_extraction
(api/extraction_service.py) and match_explanation (api/explanation_service.py)
are actually invoked today; the remaining keys are reserved for the AI-assisted
steps described in the blueprint (prompts/P05-P07, P09-P14) that don't have
callers yet.

Tests never call call_claude_structured/call_claude_text for real: they patch
this module's attributes (see api/tests/test_extraction_service.py), so
callers must look them up via the module (`ai_client.call_claude_structured(...)`)
rather than importing the function by name, or a patch would miss it.
"""

from __future__ import annotations

from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from api.ai_usage import log_ai_usage
from api.config import ANTHROPIC_API_KEY

T = TypeVar("T", bound=BaseModel)

MODEL_FOR_TASK: dict[str, str] = {
    "cv_extraction": "claude-sonnet-5",
    "vacancy_extraction": "claude-sonnet-5",
    "match_explanation": "claude-sonnet-5",
    "gap_questions": "claude-haiku-4-5-20251001",
    "clarification_questions": "claude-haiku-4-5-20251001",
    "source_classification": "claude-haiku-4-5-20251001",
    "duplicate_review_flagging": "claude-haiku-4-5-20251001",
    "sponsor_review_flagging": "claude-haiku-4-5-20251001",
    "skill_mapping": "claude-haiku-4-5-20251001",
    "occupation_mapping": "claude-haiku-4-5-20251001",
    "program_mapping": "claude-haiku-4-5-20251001",
    "industry_mapping": "claude-haiku-4-5-20251001",
}


class AIExtractionError(RuntimeError):
    """Claude's output could not be produced or did not match the target schema."""

    def __init__(self, message: str, *, raw: Any = None):
        super().__init__(message)
        self.raw = raw


def validate_tool_output(raw: Any, response_model: Type[T]) -> T:
    try:
        return response_model.model_validate(raw)
    except ValidationError as exc:
        raise AIExtractionError(f"Claude output failed schema validation: {exc}", raw=raw) from exc


def _sanitize_error_for_logging(exc: BaseException) -> str:
    """Safe-to-persist summary of exc for ai_usage_log.error_message (which has
    no retention limit -- see PROJECT_NOTES.md).

    Never the raw exception text: a pydantic ValidationError's own message
    embeds the actual submitted/extracted value that failed validation (real
    candidate/vacancy content), and other exceptions could in principle echo
    request fragments too (e.g. an API "bad request" error quoting back part
    of the input). Logs error type/category and, for a ValidationError, which
    fields failed and why -- never the values themselves.
    """
    cause = exc.__cause__ if isinstance(exc, AIExtractionError) else exc
    if isinstance(cause, ValidationError):
        field_errors = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in cause.errors())
        return f"ValidationError ({len(cause.errors())} field(s)): {field_errors}"
    return f"{type(exc).__name__}: {str(exc)[:200]}"


_client = None


def _get_client():
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise AIExtractionError("ANTHROPIC_API_KEY is not configured")
        import anthropic  # imported lazily so the module loads fine without the SDK installed
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def call_claude_structured(
    *, model: str, system: str, user: str, response_model: Type[T], max_tokens: int = 8192,
    task: Optional[str] = None, candidate_id: Optional[str] = None, vacancy_id: Optional[str] = None,
) -> T:
    """Force a tool call shaped like response_model's JSON schema, then validate it for real.

    The forced tool call keeps Claude's output syntactically well-formed; Pydantic
    validation (via validate_tool_output) is still the authoritative check, since
    JSON Schema alone can't express every rule these models enforce (e.g. the
    ANSWERED/UNKNOWN/NOT_SCORED reason-pairing on ElementValueState).

    max_tokens defaults to 8192 but callers whose expected output is large (e.g.
    extraction_service.py's per-element value_schema now pushes real vacancy/CV
    responses close to or past that) should pass a higher value explicitly --
    see PROJECT_NOTES.md's entry on this. A silently truncated (stop_reason=
    "max_tokens") tool call can still produce syntactically-valid-but-incomplete
    JSON (e.g. an empty extracted_elements list), which passes schema validation
    without ever surfacing an error -- so this is not just a latency concern.

    task/candidate_id/vacancy_id are forwarded to api/ai_usage.py's log_ai_usage
    for admin cost reporting -- optional so this signature still works for any
    future caller that doesn't care about attribution, but every current caller
    (api/extraction_service.py) does pass them. Exactly one log row is written
    per call on every path below (API exception, truncation, missing tool_use,
    schema-validation failure, or real success) -- never zero, never more than one.
    """
    client = _get_client()
    schema = response_model.model_json_schema()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "name": "submit_extraction",
                "description": "Submit the structured extraction result matching the required schema.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": "submit_extraction"},
        )
    except Exception as exc:
        log_ai_usage(
            task=task, model=model, input_tokens=0, output_tokens=0, success=False,
            talent_id=candidate_id, vacancy_id=vacancy_id, error_message=_sanitize_error_for_logging(exc),
        )
        raise

    usage = response.usage
    log_kwargs = dict(
        task=task, model=model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        talent_id=candidate_id, vacancy_id=vacancy_id,
    )

    if response.stop_reason == "max_tokens":
        # A truncated tool call can still be syntactically complete JSON (e.g. the model
        # emitted an empty extracted_elements list before running out of budget on the
        # rest) -- that passes response_model validation and would otherwise look like a
        # legitimate "nothing found" result. Surface it as a clear, loud failure instead
        # of a silent one; the caller should retry with a higher max_tokens or a shorter
        # prompt, not treat this response as trustworthy.
        error_message = (
            f"Claude response was truncated at max_tokens={max_tokens} "
            f"(output_tokens={usage.output_tokens}); result may be incomplete or empty"
        )
        log_ai_usage(**log_kwargs, success=False, error_message=error_message)
        raise AIExtractionError(error_message, raw=response.model_dump())

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        log_ai_usage(**log_kwargs, success=False, error_message="Claude response did not include a tool_use block")
        raise AIExtractionError("Claude response did not include a tool_use block", raw=response.model_dump())

    try:
        result = validate_tool_output(tool_use.input, response_model)
    except AIExtractionError as exc:
        log_ai_usage(**log_kwargs, success=False, error_message=_sanitize_error_for_logging(exc))
        raise

    log_ai_usage(**log_kwargs, success=True)
    return result


def call_claude_text(
    *, model: str, system: str, user: str, max_tokens: int = 2048,
    task: Optional[str] = None, candidate_id: Optional[str] = None, vacancy_id: Optional[str] = None,
) -> str:
    """Plain prose generation -- no forced tool call, no schema to validate against.

    For a single free-text field like JobRecommendation.explanation, where
    there's nowhere structured to put a richer response anyway (see
    api/explanation_service.py's module docstring), asking for prose directly
    is simpler and more honest than forcing structured JSON only to flatten it.

    See call_claude_structured's docstring for task/candidate_id/vacancy_id and
    the "exactly one log row per call" guarantee.
    """
    client = _get_client()

    try:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        log_ai_usage(
            task=task, model=model, input_tokens=0, output_tokens=0, success=False,
            talent_id=candidate_id, vacancy_id=vacancy_id, error_message=_sanitize_error_for_logging(exc),
        )
        raise

    usage = response.usage
    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        log_ai_usage(
            task=task, model=model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            success=False, talent_id=candidate_id, vacancy_id=vacancy_id,
            error_message="Claude response did not include a text block",
        )
        raise AIExtractionError("Claude response did not include a text block", raw=response.model_dump())

    log_ai_usage(
        task=task, model=model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        success=True, talent_id=candidate_id, vacancy_id=vacancy_id,
    )
    return "\n".join(text_blocks).strip()
