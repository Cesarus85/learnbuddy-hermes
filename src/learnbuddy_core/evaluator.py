"""Answer evaluation helpers.

The evaluator is intentionally boring and deterministic for simple exercises.
LLM-based judging can be layered on top later, but the safety-critical attempt
state should not depend on a fuzzy model call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Any
import re
import unicodedata


@dataclass(frozen=True)
class Evaluation:
    correct: bool
    attempts: int
    max_attempts: int
    exhausted: bool
    canonical_answer: str | None
    feedback: str


def normalize_answer(value: Any) -> str:
    """Normalize a short answer for deterministic comparison."""
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.strip().casefold()
    text = re.sub(r"\s+", " ", text)
    # Trim harmless sentence punctuation around short answers.
    text = text.strip(" .,!?:;\n\t")
    return text


def answer_variants(answer: Any = None, expected_answers: Iterable[Any] | None = None, aliases: Iterable[Any] | None = None) -> list[str]:
    """Return normalized accepted answer variants, preserving order."""
    raw: list[Any] = []
    if answer is not None:
        if isinstance(answer, (list, tuple, set)):
            raw.extend(answer)
        else:
            raw.append(answer)
    if expected_answers:
        raw.extend(expected_answers)
    if aliases:
        raw.extend(aliases)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        n = normalize_answer(item)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def canonical_answer(answer: Any = None, expected_answers: Iterable[Any] | None = None) -> str | None:
    """Return the human-facing canonical answer for final feedback."""
    if answer is not None and not isinstance(answer, (list, tuple, set)):
        return str(answer)
    if isinstance(answer, (list, tuple)) and answer:
        return str(answer[0])
    if expected_answers:
        for item in expected_answers:
            return str(item)
    return None


def evaluate_answer(
    user_answer: Any,
    *,
    answer: Any = None,
    expected_answers: Iterable[Any] | None = None,
    aliases: Iterable[Any] | None = None,
    previous_attempts: int = 0,
    max_attempts: int = 3,
) -> Evaluation:
    """Evaluate a single short-answer exercise and compute attempt state."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempts = previous_attempts + 1
    accepted = answer_variants(answer, expected_answers, aliases)
    normalized = normalize_answer(user_answer)
    correct = bool(normalized and normalized in accepted)
    exhausted = bool((not correct) and attempts >= max_attempts)
    canon = canonical_answer(answer, expected_answers)
    if correct:
        feedback = "Richtig! Gut gemacht."
    elif exhausted:
        if canon:
            feedback = f"Guter Versuch. Alle {max_attempts} Versuche sind jetzt aufgebraucht. Die richtige Antwort ist: {canon}."
        else:
            feedback = f"Guter Versuch. Alle {max_attempts} Versuche sind jetzt aufgebraucht."
    else:
        remaining = max_attempts - attempts
        feedback = f"Noch nicht ganz. Versuch es noch einmal. Du hast noch {remaining} Versuch{'e' if remaining != 1 else ''}."
    return Evaluation(correct=correct, attempts=attempts, max_attempts=max_attempts, exhausted=exhausted, canonical_answer=canon, feedback=feedback)
