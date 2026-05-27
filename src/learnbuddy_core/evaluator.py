"""Answer evaluation helpers.

The evaluator is intentionally boring and deterministic for simple exercises.
LLM-based judging can be layered on top later, but the safety-critical attempt
state should not depend on a fuzzy model call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    metadata: dict[str, Any] = field(default_factory=dict)


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


def _norm_number(text: Any) -> str:
    raw = "" if text is None else str(text)
    raw = unicodedata.normalize("NFKC", raw).replace(",", ".")
    matches = re.findall(r"-?\d+(?:\.\d+)?", raw)
    if not matches:
        return ""
    value = float(matches[-1])
    return str(int(value)) if value.is_integer() else str(value)


def _ordered_number_answers(text: Any) -> list[str]:
    raw = unicodedata.normalize("NFKC", "" if text is None else str(text))
    numbered = re.findall(r"(?:^|\s)\d{1,2}\s*[\.):]\s*(-?\d+(?:[,.]\d+)?)", raw)
    values = numbered or re.findall(r"-?\d+(?:[,.]\d+)?", raw)
    return [_norm_number(value) for value in values if _norm_number(value)]


def _ordered_text_answers(text: Any) -> list[str]:
    raw = " ".join(("" if text is None else str(text)).split())
    numbered = re.findall(r"(?:^|\s)\d{1,2}\s*[\.):]\s*(.*?)(?=(?:\s+\d{1,2}\s*[\.):]\s*)|$)", raw)
    if numbered:
        return [normalize_answer(part) for part in numbered if normalize_answer(part)]
    split_parts = [part for part in re.split(r"[\n;|]+", "" if text is None else str(text)) if part.strip()]
    if len(split_parts) > 1:
        return [normalize_answer(part) for part in split_parts if normalize_answer(part)]
    return [normalize_answer(raw)] if normalize_answer(raw) else []


def _ordered_expected(answer: Any = None, expected_answers: Iterable[Any] | None = None, *, prompt: str | None = None, exercise_type: str | None = None) -> list[Any]:
    if isinstance(answer, (list, tuple)) and len(answer) > 1:
        return list(answer)
    if isinstance(answer, str):
        parts = [part.strip() for part in re.split(r"[\n;|]+", answer) if part.strip()]
        if len(parts) > 1:
            return parts
        comma_parts = [part.strip() for part in answer.split(",") if part.strip()]
        if len(comma_parts) > 1 and all(re.search(r"\d", part) for part in comma_parts):
            return comma_parts
    if expected_answers is not None and exercise_type in {"calculation_batch", "batch"}:
        vals = list(expected_answers)
        if len(vals) > 1:
            return vals
    if expected_answers is not None and prompt:
        vals = list(expected_answers)
        prompt_parts = max(str(prompt).count("?"), 0)
        if prompt_parts > 1 and len(vals) == prompt_parts:
            return vals
    return []


def _looks_like_multi_part_prompt(prompt: str | None) -> bool:
    if not prompt:
        return False
    text = str(prompt)
    return text.count("?") > 1 or len([line for line in text.splitlines() if line.strip()]) > 2


def _evaluate_ordered_answer(
    user_answer: Any,
    expected: list[Any],
    *,
    previous_attempts: int,
    max_attempts: int,
) -> Evaluation:
    attempts = previous_attempts + 1
    expected_numbers = [_norm_number(value) for value in expected]
    numeric = bool(expected_numbers) and all(expected_numbers)
    if numeric:
        given = _ordered_number_answers(user_answer)
        expected_norm = expected_numbers
    else:
        given = _ordered_text_answers(user_answer)
        expected_norm = [normalize_answer(value) for value in expected]
    item_results: list[dict[str, Any]] = []
    for index, exp in enumerate(expected_norm, 1):
        got = given[index - 1] if index - 1 < len(given) else ""
        item_results.append({"index": index, "given": got, "expected": exp, "correct": bool(got and got == exp)})
    correct_count = sum(1 for row in item_results if row["correct"])
    total = len(expected_norm)
    correct = bool(total and correct_count == total)
    exhausted = bool((not correct) and attempts >= max_attempts)
    canon = ", ".join(str(value) for value in expected)
    metadata = {"score": correct_count, "total": total, "item_results": item_results}
    if correct:
        feedback = "Richtig! Alle Teilaufgaben stimmen 🎉"
    elif exhausted:
        feedback = f"Guter Versuch. Alle {max_attempts} Versuche sind jetzt aufgebraucht. Die richtigen Antworten sind: {canon}."
    else:
        wrong = [str(row["index"]) for row in item_results if not row["correct"]]
        focus = ", ".join(wrong[:4]) if wrong else f"1 bis {total}"
        if len(wrong) > 4:
            focus += " …"
        feedback = f"Fast! {correct_count}/{total} stimmen. Schau dir Nr. {focus} nochmal an. Versuch es nochmal."
    return Evaluation(correct=correct, attempts=attempts, max_attempts=max_attempts, exhausted=exhausted, canonical_answer=canon, feedback=feedback, metadata=metadata)


def evaluate_answer(
    user_answer: Any,
    *,
    answer: Any = None,
    expected_answers: Iterable[Any] | None = None,
    aliases: Iterable[Any] | None = None,
    prompt: str | None = None,
    exercise_type: str | None = None,
    subject: str | None = None,
    previous_attempts: int = 0,
    max_attempts: int = 3,
) -> Evaluation:
    """Evaluate a single short-answer exercise and compute attempt state."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempts = previous_attempts + 1
    ordered_expected = _ordered_expected(answer, expected_answers, prompt=prompt, exercise_type=exercise_type)
    if ordered_expected and (exercise_type in {"calculation_batch", "batch"} or _looks_like_multi_part_prompt(prompt) or len(_ordered_number_answers(user_answer)) > 1 or len(_ordered_text_answers(user_answer)) > 1):
        return _evaluate_ordered_answer(user_answer, ordered_expected, previous_attempts=previous_attempts, max_attempts=max_attempts)

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
