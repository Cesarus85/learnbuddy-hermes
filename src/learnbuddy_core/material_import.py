"""Public-safe worksheet/material file import helpers for LearnBuddy.

This module extracts review candidates from parent-supplied local files. It never
creates child-visible exercises and never sends messages; callers must store the
returned material through the normal parent review path.
"""
from __future__ import annotations

import json
import mimetypes
import re
import shlex
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_SUBJECTS = {"math", "german", "english", "general"}
TEXT_SUFFIXES = {".txt", ".md", ".csv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
UNSUPPORTED_IMAGE_SUFFIXES = {".heic", ".heif"}
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def extract_json_object(text_value: str) -> dict[str, Any] | None:
    raw = (text_value or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def guess_subject(text_value: str, fallback: str = "general") -> str:
    fallback = fallback if fallback in ALLOWED_SUBJECTS else "general"
    text = (text_value or "").lower()
    if any(token in text for token in ["rechne", "berechne", "runde", "zahl", "bruch", "winkel", "mathe", "="]):
        return "math"
    if any(token in text for token in ["english", "englisch", "translate", "vocabulary", "simple present", "plural"]):
        return "english"
    if any(token in text for token in ["deutsch", "grammatik", "satz", "komma", "rechtschreibung", "wortart"]):
        return "german"
    return fallback


def _candidate_lines(text_value: str) -> list[str]:
    lines = [line.strip(" •\t") for line in (text_value or "").splitlines() if line.strip()]
    candidates: list[str] = []
    pattern = re.compile(r"(^\d+[.)]|\?|=|rechne|berechne|runde|übersetze|translate|ergänze|markiere|setze)", re.I)
    for line in lines:
        if len(candidates) >= 12:
            break
        if pattern.search(line):
            candidates.append(line[:240])
    if not candidates:
        clean = re.sub(r"\s+", " ", text_value or "").strip()
        chunks = re.split(r"(?<=[.?])\s+", clean)
        candidates = [chunk[:240] for chunk in chunks if len(chunk) > 12][:8]
    return candidates


def _topic_guess(text_value: str, title: str) -> str:
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text_value or "")
    stop = {"diese", "einen", "eine", "haben", "werden", "bitte", "aufgabe", "aufgaben", "seite", "name", "klasse", "learner"}
    topic_words = [word for word, _ in Counter(word.lower() for word in words if word.lower() not in stop).most_common(6)]
    return (" / ".join(topic_words[:3]) or title or "Material")[:120]


def normalize_material_preview(data: dict[str, Any], *, title: str, fallback_subject: str = "general") -> dict[str, Any]:
    subject = str(data.get("subject") or fallback_subject or "general").lower().strip()
    if subject not in ALLOWED_SUBJECTS:
        subject = "general"
    raw_candidates = data.get("task_candidates") or data.get("tasks") or data.get("questions") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [item.strip() for item in re.split(r"\n+|(?<=\?)\s+", raw_candidates) if item.strip()]
    candidates = [str(item).strip()[:240] for item in raw_candidates if str(item).strip()][:12]
    text_excerpt = str(data.get("text_excerpt") or data.get("ocr_text") or data.get("text") or "").strip()
    if not candidates and text_excerpt:
        candidates = _candidate_lines(text_excerpt)
    if not text_excerpt and candidates:
        text_excerpt = "\n".join(candidates)
    warnings = data.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    warnings = [str(item).strip()[:240] for item in warnings if str(item).strip()][:8]
    clean = re.sub(r"\s+", " ", text_excerpt).strip()
    return {
        "subject": subject,
        "topic_guess": str(data.get("topic_guess") or data.get("topic") or _topic_guess(clean, title))[:120],
        "text_excerpt": clean[:4000],
        "text_chars": len(text_excerpt),
        "task_candidates": candidates,
        "task_count": len(candidates),
        "warnings": warnings,
        "ready_for_parent_review": bool(candidates),
    }


def preview_from_text(text_value: str, *, title: str, fallback_subject: str = "general") -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text_value or "").strip()
    candidates = _candidate_lines(text_value)
    return {
        "subject": guess_subject("\n".join([title, text_value]), fallback_subject),
        "topic_guess": _topic_guess(text_value, title),
        "text_excerpt": clean[:4000],
        "text_chars": len(text_value or ""),
        "task_candidates": candidates,
        "task_count": len(candidates),
        "warnings": [],
        "ready_for_parent_review": bool(candidates),
    }


def run_ocr_command(path: Path, command: str, *, title: str, fallback_subject: str) -> tuple[str, dict[str, Any]]:
    try:
        cp = subprocess.run(
            shlex.split(command) + [str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except Exception as exc:
        return "", {"status": "error", "provider": "command", "warning": f"ocr_command_failed:{type(exc).__name__}"}
    if cp.returncode != 0:
        return "", {"status": "error", "provider": "command", "warning": "ocr_command_nonzero", "stderr": (cp.stderr or cp.stdout or "")[:500]}
    data = extract_json_object(cp.stdout)
    if data:
        preview = normalize_material_preview(data, title=title, fallback_subject=fallback_subject)
        return preview.get("text_excerpt") or "\n".join(preview.get("task_candidates") or []), {"status": "ok", "provider": "command", "vision_preview": preview}
    text_value = cp.stdout.strip()
    return text_value, {"status": "ok" if text_value else "empty", "provider": "command"}


def extract_pdf_text(path: Path) -> tuple[str, dict[str, Any]]:
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        cp = subprocess.run([pdftotext, "-layout", str(path), "-"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
        if cp.returncode == 0 and cp.stdout.strip():
            return cp.stdout, {"status": "ok", "provider": "pdftotext"}
        return "", {"status": "error", "provider": "pdftotext", "warning": "pdf_text_extraction_failed", "stderr": (cp.stderr or cp.stdout or "")[:500]}
    try:
        import fitz  # type: ignore
    except Exception:
        return "", {"status": "unavailable", "provider": "pdf", "warning": "pdftotext_or_pymupdf_required"}
    try:
        with fitz.open(str(path)) as doc:  # type: ignore[attr-defined]
            text_value = "\n".join(page.get_text() for page in doc)
        return text_value, {"status": "ok" if text_value.strip() else "empty", "provider": "pymupdf"}
    except Exception as exc:
        return "", {"status": "error", "provider": "pymupdf", "warning": f"pdf_extraction_failed:{type(exc).__name__}"}


def build_material_from_file(
    file_path: str | Path,
    *,
    title: str,
    subject: str = "general",
    notes: str = "",
    ocr_command: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    path = Path(file_path).expanduser()
    if not title.strip():
        return {"status": "missing_title", "error": "material file import requires title"}
    if not path.exists() or not path.is_file():
        return {"status": "missing_file", "error": "material file does not exist", "file_path": str(path)}
    size = path.stat().st_size
    if size <= 0:
        return {"status": "empty_file", "error": "material file is empty", "file_path": str(path)}
    if size > max_bytes:
        return {"status": "file_too_large", "error": "material file exceeds max_bytes", "file_path": str(path), "size": size, "max_bytes": max_bytes}

    fallback_subject = subject if subject in ALLOWED_SUBJECTS else "general"
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(str(path))[0]
    source_type = "unknown"
    text_value = ""
    extraction: dict[str, Any]

    if suffix in TEXT_SUFFIXES:
        source_type = "text"
        text_value = path.read_text(encoding="utf-8", errors="replace")
        extraction = {"status": "ok", "provider": "file_text"}
    elif suffix == ".pdf":
        source_type = "pdf"
        text_value, extraction = extract_pdf_text(path)
    elif suffix in IMAGE_SUFFIXES:
        source_type = "image"
        if not ocr_command:
            return {
                "status": "ocr_unavailable",
                "error": "image material import requires --ocr-command or LEARNBUDDY_MATERIAL_OCR_COMMAND",
                "file_path": str(path),
                "source_type": source_type,
            }
        text_value, extraction = run_ocr_command(path, ocr_command, title=title, fallback_subject=fallback_subject)
    elif suffix in UNSUPPORTED_IMAGE_SUFFIXES:
        return {"status": "unsupported_file", "error": "HEIC/HEIF is not decoded; export or send JPG/PNG/WebP", "file_path": str(path), "suffix": suffix}
    else:
        return {"status": "unsupported_file", "error": "unsupported material file type", "file_path": str(path), "suffix": suffix}

    if extraction.get("status") not in {"ok", "empty"}:
        return {"status": str(extraction.get("status") or "extraction_failed"), "error": str(extraction.get("warning") or "material extraction failed"), "file_path": str(path), "source_type": source_type, "extraction": extraction}

    vision_preview = extraction.get("vision_preview") if isinstance(extraction.get("vision_preview"), dict) else None
    preview = vision_preview or preview_from_text(text_value, title=title, fallback_subject=fallback_subject)
    if not preview.get("text_excerpt") and text_value:
        preview["text_excerpt"] = re.sub(r"\s+", " ", text_value).strip()[:4000]
    material = {
        "title": title.strip(),
        "subject": preview.get("subject") if preview.get("subject") in ALLOWED_SUBJECTS else fallback_subject,
        "source_type": source_type,
        "text_excerpt": preview.get("text_excerpt") or "",
        "task_candidates": preview.get("task_candidates") or [],
        "notes": notes or "",
        "metadata": {
            "source": "material_file_import",
            "filename": path.name,
            "mime_type": mime,
            "size": size,
            "extraction": {key: value for key, value in extraction.items() if key != "vision_preview"},
            "preview": preview,
        },
    }
    return {"status": "ok", "file_path": str(path), "source_type": source_type, "extraction": material["metadata"]["extraction"], "preview": preview, "material": material}
