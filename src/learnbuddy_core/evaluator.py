"""Answer evaluation helpers.

The evaluator is intentionally boring and deterministic for simple exercises.
LLM-based judging can be layered on top later, but the safety-critical attempt
state should not depend on a fuzzy model call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Any
import json
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


def _json_expected_payload(value: Any) -> dict[str, Any] | None:
    """Parse legacy JSON-encoded answer payloads such as {"expected": [...]}.

    Some parent-created exercises accidentally stored the expected-answer object as
    a JSON string in ``answer``. Treat that as data, not as the literal answer.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _flatten_expected_items(value: Any) -> list[Any]:
    payload = _json_expected_payload(value)
    if payload is not None:
        for key in ("expected", "expected_answers", "answers", "aliases"):
            nested = payload.get(key)
            if nested is not None:
                return _flatten_expected_items(nested)
        if payload.get("answer") is not None:
            return _flatten_expected_items(payload.get("answer"))
        return []
    if isinstance(value, dict):
        for key in ("expected", "expected_answers", "answers", "aliases", "answer"):
            nested = value.get(key)
            if nested is not None:
                return _flatten_expected_items(nested)
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[Any] = []
        for item in value:
            out.extend(_flatten_expected_items(item))
        return out
    return [value] if value is not None else []


def _expand_english_infinitive_variants(variants: list[str], *, subject: str | None = None, prompt: str | None = None) -> list[str]:
    """Accept both bare verb and ``to`` infinitive for English vocab prompts."""
    text = f"{subject or ''} {prompt or ''}".casefold()
    if "english" not in text and "englisch" not in text:
        return variants
    out = list(variants)
    seen = set(out)
    for item in variants:
        if item.startswith("to ") and len(item) > 3:
            bare = item[3:].strip()
            if bare and bare not in seen:
                seen.add(bare)
                out.append(bare)
        else:
            with_to = f"to {item}".strip()
            if re.fullmatch(r"[a-z][a-z' -]*", item) and with_to not in seen:
                seen.add(with_to)
                out.append(with_to)
    return out


def answer_variants(answer: Any = None, expected_answers: Iterable[Any] | None = None, aliases: Iterable[Any] | None = None, *, subject: str | None = None, prompt: str | None = None) -> list[str]:
    """Return normalized accepted answer variants, preserving order."""
    raw: list[Any] = []
    raw.extend(_flatten_expected_items(answer))
    raw.extend(_flatten_expected_items(expected_answers))
    raw.extend(_flatten_expected_items(aliases))
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        n = normalize_answer(item)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return _expand_english_infinitive_variants(out, subject=subject, prompt=prompt)


def canonical_answer(answer: Any = None, expected_answers: Iterable[Any] | None = None) -> str | None:
    """Return the human-facing canonical answer for final feedback."""
    for item in _flatten_expected_items(answer):
        return str(item)
    for item in _flatten_expected_items(expected_answers):
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


def _ordered_number_answer_pairs(text: Any) -> list[tuple[int, str]]:
    raw = unicodedata.normalize("NFKC", "" if text is None else str(text))
    pairs = re.findall(r"(?:^|\s)(\d{1,2})\s*[\.):]\s*(-?\d+(?:[,.]\d+)?)", raw)
    out: list[tuple[int, str]] = []
    for index, value in pairs:
        normalized = _norm_number(value)
        if normalized:
            out.append((int(index), normalized))
    return out


def _ordered_text_answers(text: Any) -> list[str]:
    raw = " ".join(("" if text is None else str(text)).split())
    numbered = re.findall(r"(?:^|\s)\d{1,2}\s*[\.):]\s*(.*?)(?=(?:\s+\d{1,2}\s*[\.):]\s*)|$)", raw)
    if numbered:
        return [normalize_answer(part) for part in numbered if normalize_answer(part)]
    split_parts = [part for part in re.split(r"[\n;|]+", "" if text is None else str(text)) if part.strip()]
    if len(split_parts) > 1:
        return [normalize_answer(part) for part in split_parts if normalize_answer(part)]
    return [normalize_answer(raw)] if normalize_answer(raw) else []


def _ordered_text_answer_pairs(text: Any) -> list[tuple[int, str]]:
    raw = " ".join(("" if text is None else str(text)).split())
    pairs = re.findall(r"(?:^|\s)(\d{1,2})\s*[\.):]\s*(.*?)(?=(?:\s+\d{1,2}\s*[\.):]\s*)|$)", raw)
    out: list[tuple[int, str]] = []
    for index, value in pairs:
        normalized = normalize_answer(value)
        if normalized:
            out.append((int(index), normalized))
    return out


def _looks_like_unordered_all_prompt(prompt: str | None) -> bool:
    normalized = normalize_answer(prompt)
    return any(phrase in normalized for phrase in (
        "nenne alle",
        "alle nachbarländer",
        "alle nachbarlaender",
        "name all",
        "list all",
    ))


def _unordered_text_answers(text: Any) -> list[str]:
    raw = "" if text is None else str(text)
    numbered = _ordered_text_answers(raw)
    if len(numbered) > 1:
        return numbered
    parts = [
        normalize_answer(re.sub(r"^\s*\d{1,2}\s*[\.):]\s*", "", part))
        for part in re.split(r"[,;|\n]+", raw)
    ]
    return [part for part in parts if part]


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
        if prompt_parts > 1 and len(vals) > prompt_parts and len(vals) % prompt_parts == 0:
            chunk = len(vals) // prompt_parts
            return [vals[i * chunk:(i + 1) * chunk] for i in range(prompt_parts)]
    return []


def _normalize_ordered_expected_item(value: Any, *, numeric: bool) -> list[str]:
    raw_values = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[str] = []
    for raw in raw_values:
        normalized = _norm_number(raw) if numeric else normalize_answer(raw)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _ordered_expected_label(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " / ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _looks_like_multi_part_prompt(prompt: str | None) -> bool:
    if not prompt:
        return False
    text = str(prompt)
    return text.count("?") > 1 or len([line for line in text.splitlines() if line.strip()]) > 2


def _evaluate_unordered_answer(
    user_answer: Any,
    expected: list[Any],
    *,
    previous_attempts: int,
    max_attempts: int,
    previous_item_results: Iterable[dict[str, Any]] | None = None,
) -> Evaluation:
    attempts = previous_attempts + 1
    expected_norm = [_normalize_ordered_expected_item(value, numeric=False) for value in expected]
    matched: dict[int, str] = {}
    for row in previous_item_results or []:
        if not isinstance(row, dict) or row.get("correct") is not True:
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if 1 <= index <= len(expected_norm):
            matched[index] = str(row.get("given") or "")
    for value in _unordered_text_answers(user_answer):
        for index, aliases in enumerate(expected_norm, 1):
            if index not in matched and value in aliases:
                matched[index] = value
                break
    item_results = [
        {
            "index": index,
            "given": matched.get(index, ""),
            "expected": _ordered_expected_label(expected[index - 1]),
            "correct": index in matched,
        }
        for index in range(1, len(expected_norm) + 1)
    ]
    correct_count = len(matched)
    total = len(expected_norm)
    correct = bool(total and correct_count == total)
    exhausted = bool((not correct) and attempts >= max_attempts)
    canon = ", ".join(_ordered_expected_label(value) for value in expected)
    metadata = {"score": correct_count, "total": total, "item_results": item_results}
    if correct:
        feedback = "Richtig! Du hast alle genannt 🎉"
    elif exhausted:
        feedback = f"Guter Versuch. Die vollständige Lösung ist: {canon}."
    else:
        feedback = f"Fast! {correct_count}/{total} stimmen. Es fehlen noch {total - correct_count}. Versuch es nochmal."
    return Evaluation(
        correct=correct,
        attempts=attempts,
        max_attempts=max_attempts,
        exhausted=exhausted,
        canonical_answer=canon,
        feedback=feedback,
        metadata=metadata,
    )


def _evaluate_ordered_answer(
    user_answer: Any,
    expected: list[Any],
    *,
    previous_attempts: int,
    max_attempts: int,
    previous_item_results: Iterable[dict[str, Any]] | None = None,
) -> Evaluation:
    attempts = previous_attempts + 1
    expected_numbers = [_norm_number(value) for value in expected]
    numeric = bool(expected_numbers) and all(expected_numbers)
    if numeric:
        explicit_pairs = _ordered_number_answer_pairs(user_answer)
        given = _ordered_number_answers(user_answer)
        expected_norm = [_normalize_ordered_expected_item(value, numeric=True) for value in expected]
    else:
        explicit_pairs = _ordered_text_answer_pairs(user_answer)
        given = _ordered_text_answers(user_answer)
        expected_norm = [_normalize_ordered_expected_item(value, numeric=False) for value in expected]

    previous_correct: dict[int, dict[str, Any]] = {}
    for row in previous_item_results or []:
        if not isinstance(row, dict) or row.get("correct") is not True:
            continue
        raw_index = row.get("index")
        if raw_index is None:
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= len(expected_norm):
            continue
        previous_correct[index] = {
            "index": index,
            "given": str(row.get("given") or ""),
            "expected": _ordered_expected_label(expected[index - 1]),
            "correct": True,
        }

    item_results: list[dict[str, Any]] = [
        previous_correct.get(index, {"index": index, "given": "", "expected": _ordered_expected_label(expected[index - 1]), "correct": False})
        for index in range(1, len(expected_norm) + 1)
    ]
    explicit = {index: value for index, value in explicit_pairs if 1 <= index <= len(expected_norm)}
    open_indices = [index for index in range(1, len(expected_norm) + 1) if index not in previous_correct]
    assignments: dict[int, str] = {}
    if explicit:
        assignments = explicit
    elif given:
        if previous_correct and len(given) != len(expected_norm):
            targets = open_indices
        else:
            targets = list(range(1, len(expected_norm) + 1))
        assignments = {index: got for index, got in zip(targets, given)}

    for index, aliases in enumerate(expected_norm, 1):
        if index not in assignments:
            continue
        got = assignments[index]
        item_results[index - 1] = {
            "index": index,
            "given": got,
            "expected": _ordered_expected_label(expected[index - 1]),
            "correct": bool(got and got in aliases),
        }
    correct_count = sum(1 for row in item_results if row["correct"])
    total = len(expected_norm)
    correct = bool(total and correct_count == total)
    exhausted = bool((not correct) and attempts >= max_attempts)
    canon = ", ".join(_ordered_expected_label(value) for value in expected)
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
    previous_item_results: Iterable[dict[str, Any]] | None = None,
) -> Evaluation:
    """Evaluate a single short-answer exercise and compute attempt state."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempts = previous_attempts + 1
    if expected_answers is not None and _looks_like_unordered_all_prompt(prompt):
        unordered_expected = list(expected_answers)
        if len(unordered_expected) > 1:
            return _evaluate_unordered_answer(
                user_answer,
                unordered_expected,
                previous_attempts=previous_attempts,
                max_attempts=max_attempts,
                previous_item_results=previous_item_results,
            )
    ordered_expected = _ordered_expected(answer, expected_answers, prompt=prompt, exercise_type=exercise_type)
    if ordered_expected and (
        previous_item_results
        or exercise_type in {"calculation_batch", "batch"}
        or _looks_like_multi_part_prompt(prompt)
        or len(_ordered_number_answers(user_answer)) > 1
        or len(_ordered_text_answers(user_answer)) > 1
    ):
        return _evaluate_ordered_answer(
            user_answer,
            ordered_expected,
            previous_attempts=previous_attempts,
            max_attempts=max_attempts,
            previous_item_results=previous_item_results,
        )

    accepted = answer_variants(answer, expected_answers, aliases, subject=subject, prompt=prompt)
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
