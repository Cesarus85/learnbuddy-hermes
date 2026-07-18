"""Parent-facing message formatting for answer notifications.

Keep these messages transport-agnostic: plain text with clear sections works in
Telegram, logs, and dry-run outputs without relying on Markdown parse modes.
"""
from __future__ import annotations

from typing import Any


SUBJECT_LABELS = {
    "math": "Mathe",
    "mathe": "Mathe",
    "german": "Deutsch",
    "deutsch": "Deutsch",
    "english": "Englisch",
    "englisch": "Englisch",
    "general": "Allgemein",
}


def one_line(value: Any, *, max_len: int = 360) -> str:
    """Collapse whitespace and cap long parent-facing fields."""
    text = " ".join(str(value or "—").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def subject_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Allgemein"
    return SUBJECT_LABELS.get(raw.lower(), raw)


def _attempt_text(attempts: Any, max_attempts: Any, *, exhausted: bool) -> str | None:
    if attempts in (None, ""):
        return None
    if max_attempts not in (None, ""):
        text = f"{attempts}/{max_attempts}"
    else:
        text = str(attempts)
    if exhausted:
        text += " — alle Versuche aufgebraucht"
    return text


def _metadata_value(result: dict[str, Any], key: str) -> Any:
    raw_metadata = result.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    if key in metadata:
        return metadata.get(key)
    return result.get(key)


def _wrong_items(result: dict[str, Any]) -> list[str]:
    item_results = _metadata_value(result, "item_results")
    if not isinstance(item_results, list):
        return []
    wrong: list[str] = []
    for item in item_results:
        if isinstance(item, dict) and not item.get("correct"):
            index = item.get("index")
            if index not in (None, ""):
                wrong.append(str(index))
    return wrong


def result_status_text(result: dict[str, Any]) -> str:
    """Return a compact status phrase with an icon for parent scans."""
    if result.get("result") == "exhausted" or result.get("exhausted"):
        return "⛔ nicht richtig"
    if result.get("correct") is True:
        return "✅ richtig"
    return "❌ noch nicht richtig"


def format_parent_answer_notification(
    *,
    agent_name: str,
    child_name: str,
    subject: Any,
    prompt: Any,
    answer: Any,
    result: dict[str, Any],
) -> str:
    """Format a child-answer notification as readable plain-text sections."""
    lines = [
        f"📚 {agent_name} · {subject_label(subject)}",
        f"{child_name} hat geantwortet",
        "",
        "Aufgabe",
        one_line(prompt, max_len=700),
        "",
        f"Antwort von {child_name}",
        one_line(answer, max_len=500),
        "",
        "Auswertung",
        f"• Status: {result_status_text(result)}",
    ]

    attempt_text = _attempt_text(result.get("attempts"), result.get("max_attempts"), exhausted=bool(result.get("exhausted") or result.get("result") == "exhausted"))
    if attempt_text:
        lines.append(f"• Versuch: {attempt_text}")

    score = _metadata_value(result, "score")
    total = _metadata_value(result, "total")
    if score not in (None, "") and total not in (None, ""):
        lines.append(f"• Teilaufgaben: {score}/{total} richtig")

    wrong = _wrong_items(result)
    if wrong:
        lines.append(f"• Nochmal anschauen: Nr. {', '.join(wrong[:6])}{' …' if len(wrong) > 6 else ''}")

    return "\n".join(lines)
