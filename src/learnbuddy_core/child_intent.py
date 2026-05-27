"""Semantic child-intent classification for LearnBuddy.

Two-stage classifier:
  1. Fast preflight: exact / normalized phrase match (no LLM needed).
  2. Semantic fallback: LLM-backed classification for free-form child text.

The classifier returns one of:
  - ``"repeat"`` — child wants the current prompt re-sent.
  - ``"help"``   — child is stuck / asks for help.
  - ``"next"``   — child wants a new exercise.
  - ``None``     — not a control message; treat as a regular answer.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phrase-based preflight (fast, no network)
# ---------------------------------------------------------------------------

_REPEAT_PHRASES: frozenset[str] = frozenset({
    "nochmal", "noch mal", "nochmal bitte", "noch mal bitte",
    "bitte nochmal", "bitte noch mal", "nochmal senden", "noch mal senden",
    "wiederholen", "bitte wiederholen", "zeige nochmal", "zeig nochmal",
    "aufgabe nochmal", "nochmal zeigen", "zeige die aufgabe nochmal",
    "nochmal die aufgabe", "nochmal zeigen bitte",
})

_HELP_PHRASES: frozenset[str] = frozenset({
    "hilfe", "hilf mir", "ich brauche hilfe", "ich brauch hilfe",
    "ich weiss nicht", "weiss nicht", "ich weiss es nicht",
    "keine ahnung", "ich komme nicht weiter", "ich verstehe es nicht",
    "kapier ich nicht", "kapiere ich nicht", "check ich nicht",
    " verstehe nicht", "garnicht verstanden", "gar nicht verstanden",
})

_NEXT_PHRASES: frozenset[str] = frozenset({
    "noch eine", "noch eine bitte", "noch ne", "noch ne bitte",
    "naechste", "naechste bitte", "nächste", "nächste bitte",
    "neue aufgabe", "neue aufgabe bitte",
    "noch eine aufgabe", "noch eine aufgabe bitte",
    "noch ne aufgabe", "noch ne aufgabe bitte",
    "weiter", "weiter bitte", "noch mehr", "mehr bitte",
    "noch eins", "noch eins bitte", "naechstes", "nächstes",
})

_ALL_PHRASES: dict[str, str] = {}
for _p in _REPEAT_PHRASES:
    _ALL_PHRASES[_p] = "repeat"
for _p in _HELP_PHRASES:
    _ALL_PHRASES[_p] = "help"
for _p in _NEXT_PHRASES:
    _ALL_PHRASES[_p] = "next"


def _normalize(text: str) -> str:
    return " ".join(
        text.lower()
        .replace("ß", "ss")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .strip(" .!?¡¿:;,-_\n\t")
        .split()
    )


def classify_preflight(text: str) -> str | None:
    """Exact / normalized phrase match. Returns intent or None."""
    normalized = _normalize(text)
    if not normalized:
        return None
    if normalized in _ALL_PHRASES:
        return _ALL_PHRASES[normalized]
    # Check if any phrase is a substring of the normalized text
    # for slightly more flexible matching
    for phrase, intent in _ALL_PHRASES.items():
        if phrase in normalized and len(normalized) < len(phrase) + 15:
            return intent
    return None


# ---------------------------------------------------------------------------
# LLM-backed semantic fallback
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a child-intent classifier for a learning app. "
    "Classify the child\'s message into exactly one category.\n\n"
    "Categories:\n"
    "- repeat: child wants the current exercise prompt shown again "
    "(e.g. showing the task, reading it again, resend).\n"
    "- help: child is stuck, confused, doesn\'t know the answer, "
    "asks for help or a hint.\n"
    "- next: child wants a new/different exercise, wants to continue, "
    "wants more practice.\n"
    "- answer: the message is an attempt to answer the exercise question "
    "(a number, a word, a sentence that could be an answer).\n\n"
    "Respond with ONLY the category word, nothing else. "
    "No explanation, no punctuation."
)

Transport = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class IntentClassifierConfig:
    """Configuration for the LLM-backed intent classifier."""

    enabled: bool = False
    provider: str = "openai"
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "LEARNBUDDY_INTENT_API_KEY"
    timeout: int = 8
    max_text_length: int = 200


def _build_llm_payload(text: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text[:200]},
        ],
        "max_tokens": 10,
        "temperature": 0.0,
    }


def _parse_llm_response(body: dict[str, Any]) -> str | None:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    content = ""
    message = choices[0].get("message")
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip().lower()
    if content in {"repeat", "help", "next"}:
        return content
    if content == "answer":
        return None  # treat answer as "not a control message"
    return None


def classify_semantic(
    text: str,
    config: IntentClassifierConfig,
    *,
    transport: Transport | None = None,
) -> str | None:
    """LLM-backed intent classification. Returns intent or None."""
    if not config.enabled:
        return None
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        return None

    payload = _build_llm_payload(text, config.model)
    url = f"{config.api_base.rstrip('/')}/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    _transport = transport or _default_transport
    try:
        response_body = _transport(url, payload, req, config.timeout)
        return _parse_llm_response(response_body)
    except Exception:
        logger.debug("Intent classifier LLM call failed", exc_info=True)
        return None


def _default_transport(
    url: str,
    payload: dict[str, Any],
    request: urllib.request.Request,
    timeout: int,
) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Unified two-stage classifier
# ---------------------------------------------------------------------------

def classify_child_intent(
    text: str,
    config: IntentClassifierConfig | None = None,
    *,
    transport: Transport | None = None,
) -> str | None:
    """Two-stage child-intent classification.

    1. Fast preflight (phrase match).
    2. If preflight returns None and semantic classifier is configured, try LLM.

    Returns one of ``"repeat"``, ``"help"``, ``"next"``, or ``None``.
    """
    preflight = classify_preflight(text)
    if preflight is not None:
        return preflight
    if config is not None:
        return classify_semantic(text, config, transport=transport)
    return None
