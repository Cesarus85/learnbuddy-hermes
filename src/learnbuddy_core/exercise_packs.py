"""Built-in public-safe exercise packs for LearnBuddy."""
from __future__ import annotations

from collections import Counter
from importlib import resources
from typing import Any
import json

from .runtime import LearnBuddyRuntime

DEFAULT_PACK = "de/bavaria-realschule-grade-5"


def normalize_pack_name(name: str | None) -> str:
    """Return the canonical exercise-pack name used by the CLI and docs."""
    raw = (name or DEFAULT_PACK).strip().replace("\\", "/")
    aliases = {
        "bavaria-realschule-grade-5": DEFAULT_PACK,
        "de/grade-5-bavaria-realschule": DEFAULT_PACK,
        "de/by-rs5": DEFAULT_PACK,
    }
    return aliases.get(raw, raw)


def available_packs() -> list[str]:
    return [DEFAULT_PACK]


def load_exercise_pack(name: str | None = None) -> list[dict[str, Any]]:
    """Load a bundled public-safe JSONL exercise pack."""
    pack = normalize_pack_name(name)
    if pack not in available_packs():
        raise ValueError(f"unknown exercise pack: {pack}")
    relative = f"exercise_packs/{pack}.jsonl"
    text = (resources.files("learnbuddy_core") / relative).read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"invalid exercise pack row {line_number}: expected object")
        _validate_pack_row(value, line_number=line_number, pack=pack)
        rows.append(value)
    return rows


def import_exercise_pack(runtime: LearnBuddyRuntime, name: str | None = None) -> dict[str, Any]:
    """Import a bundled exercise pack into runtime storage, skipping existing ids."""
    pack = normalize_pack_name(name)
    rows = load_exercise_pack(pack)
    existing_ids = {str(row.get("id")) for row in runtime.exercises() if row.get("id")}
    imported: list[dict[str, Any]] = []
    skipped_existing = 0
    for row in rows:
        if str(row.get("id")) in existing_ids:
            skipped_existing += 1
            continue
        imported.append(runtime.add_exercise(dict(row)))
        existing_ids.add(str(row.get("id")))
    subjects = Counter(str(row.get("subject") or "general") for row in rows)
    return {
        "status": "imported" if imported else "already_imported",
        "pack": pack,
        "available_packs": available_packs(),
        "total": len(rows),
        "imported": len(imported),
        "skipped_existing": skipped_existing,
        "subjects": dict(sorted(subjects.items())),
        "exercise_ids": [row["id"] for row in imported],
    }


def _validate_pack_row(row: dict[str, Any], *, line_number: int, pack: str) -> None:
    required = {"id", "subject", "type", "topic", "prompt", "difficulty", "hint", "success", "school_context"}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"invalid exercise pack {pack} row {line_number}: missing {','.join(missing)}")
    if "answer" not in row and "expected_answers" not in row:
        raise ValueError(f"invalid exercise pack {pack} row {line_number}: missing answer or expected_answers")
    if row.get("subject") not in {"math", "german", "english"}:
        raise ValueError(f"invalid exercise pack {pack} row {line_number}: unsupported subject")
    difficulty = int(row.get("difficulty") or 0)
    if difficulty < 1 or difficulty > 5:
        raise ValueError(f"invalid exercise pack {pack} row {line_number}: difficulty out of range")
