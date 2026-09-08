"""Thin wrapper around the Claude API (Anthropic Python SDK) for the AI
Recommendation System. Isolated in its own module so `recommendation_service`
stays testable/readable without an SDK import mixed into its logic.
"""
import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger("prioriton.llm")


class LLMNotConfiguredError(Exception):
    """Raised when no ANTHROPIC_API_KEY is set - the recommendations feature
    degrades to a clear "not configured" response instead of crashing."""


class LLMResponseError(Exception):
    """Raised when the model's reply couldn't be parsed as the expected JSON
    shape, even after one retry with a stricter reminder."""


SYSTEM_PROMPT = """\
You are a study coach embedded in a student productivity app called Prioriton. \
You are given one week of a student's real, locally-tracked data: their \
courses, grades, study-time-tracker hours per course, and how many days \
before each assignment's due date they started working on it. Your job is \
to turn that into a short list of specific, actionable recommendations.

Rules:
- Ground every claim in the numbers you were given. Never invent a course, \
grade, or hour figure that isn't in the data.
- Prefer concrete comparisons over vague advice, e.g. "You're spending 2.1 \
hours/week on MATH 241, which is 3.4 hours less than your average across \
other courses" or "Assignments in CS 225 have taken you 4 hours on average \
in the past - start this one now to finish comfortably before it's due."
- Each item must name a `kind`: "study_time", "grade", "assignment_start", \
"productivity", or "general".
- Each item gets a `priority`: 1 (address this first), 2 (normal), or 3 \
(minor/positive note - it's fine to point out something going well).
- Return 3 to 6 items. Prefer fewer, sharper items over padding the list.
- Respond with ONLY a JSON array, no prose before or after, no markdown code \
fences. Each element: {"course_name": string|null, "kind": string, \
"message": string, "priority": integer}.
"""


def _client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise LLMNotConfiguredError("The 'anthropic' package isn't installed.") from exc

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError(
            "ANTHROPIC_API_KEY isn't set. Add it to backend/.env to enable AI recommendations."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key), settings.anthropic_model


def _extract_json_array(text: str) -> Any:
    """Claude is instructed to return only a JSON array, but this strips any
    accidental markdown code fences before parsing, since that's the most
    common way a strict-JSON instruction still gets lightly wrapped."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    return json.loads(stripped)


def generate_recommendations(summary: dict) -> list[dict]:
    """Sends the analytics summary to Claude and returns a validated list of
    recommendation item dicts. Retries once with a stricter reminder if the
    first reply doesn't parse as the expected JSON array."""
    client, model = _client()
    user_message = (
        "Here is this week's tracked data (JSON). Generate recommendations per the rules above:\n\n"
        + json.dumps(summary, indent=2)
    )

    def _call(extra_reminder: str = "") -> list[dict]:
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=SYSTEM_PROMPT + extra_reminder,
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        parsed = _extract_json_array(text)
        if not isinstance(parsed, list):
            raise LLMResponseError("Model response was valid JSON but not a JSON array.")
        return parsed

    try:
        return _call()
    except (json.JSONDecodeError, LLMResponseError) as exc:
        logger.warning("First recommendation generation failed to parse (%s), retrying once", exc)
        try:
            return _call(
                "\n\nYour previous reply did not parse as a raw JSON array. "
                "Reply with ONLY the JSON array this time - no other text."
            )
        except (json.JSONDecodeError, LLMResponseError) as retry_exc:
            raise LLMResponseError(f"Model reply could not be parsed after a retry: {retry_exc}") from retry_exc
