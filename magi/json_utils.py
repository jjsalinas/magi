"""Helpers for pulling a structured MAGI decision out of a raw model reply."""

import json
import re
from typing import Any

_CODE_FENCE_START = re.compile(r"^```(?:json)?", re.IGNORECASE)
_CODE_FENCE_END = re.compile(r"```$")
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_DECISION_FIELD = re.compile(r'"decision"\s*:\s*"?(YES|NO)"?')


def clean_json_response(text: str) -> str:
    """Strip an optional ```json ... ``` code fence from a model reply."""
    text = text.strip()

    if text.startswith("```"):
        text = _CODE_FENCE_START.sub("", text)
        text = _CODE_FENCE_END.sub("", text)
        text = text.strip()

    return text


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from a model reply.

    Tries a direct parse first, then falls back to locating the first
    `{...}` span in the text (models sometimes wrap JSON in commentary).
    """
    text = clean_json_response(text)

    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    match = _JSON_OBJECT.search(text)
    if not match:
        return None

    return _try_parse(match.group(0))


def _try_parse(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def normalize_decision(value: Any) -> str | None:
    """Coerce a raw value into 'YES' / 'NO', or None if it's neither."""
    if value is None:
        return None

    decision = str(value).strip().upper()

    return decision if decision in {"YES", "NO"} else None


def clamp_confidence(value: Any) -> float:
    """Coerce a raw value into a float in [0, 1], defaulting to 0.5."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5

    return max(0.0, min(1.0, confidence))


def extract_binary_decision(text: str) -> str | None:
    """Last-resort decision extraction from free-form (non-JSON) text."""
    upper = text.upper()

    match = _DECISION_FIELD.search(upper)
    if match:
        return match.group(1)

    has_yes = re.search(r"\bYES\b", upper) is not None
    has_no = re.search(r"\bNO\b", upper) is not None

    if has_yes and not has_no:
        return "YES"

    if has_no and not has_yes:
        return "NO"

    return None
