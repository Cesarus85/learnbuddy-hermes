"""Hermes plugin entrypoint for LearnBuddy.

Only generic, tested LearnBuddy core pieces live here. Production family-specific
plugins must not be copied into this repository.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from learnbuddy_core.cli import _auto_sessions_today, _inside_allowed_hours, _parse_datetime, run_daily_parent_status, run_weekly_parent_status
from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.delivery import DeliveryMessage, delivery_adapter_from_config
from learnbuddy_core.material_import import build_material_from_file
from learnbuddy_core.notifier import ParentNotifier
from learnbuddy_core.runtime import LearnBuddyRuntime
from learnbuddy_core.telegram_answer_watcher import _dispatch_child_requested_next_exercise, _with_metadata

PLUGIN_NAME = "learnbuddy-learning"
PLUGIN_VERSION = "0.1.2-alpha"

PARENT_COMMAND_CONTRACTS: list[dict[str, Any]] = [
    {
        "operation": "current_status",
        "tool": "learnbuddy_learning_status",
        "examples": ["Status", "Was ist offen?", "Zeig die Queue", "Hat Learner gerade eine offene Aufgabe?"],
        "policy": "Read-only. Use only for current pending/queue questions; it does not answer whether Learner recently replied.",
    },
    {
        "operation": "answer_status",
        "tool": "learnbuddy_parent_answer_status",
        "examples": ["Hat Learner geantwortet?", "Wie war die Antwort?", "Status der beantworteten Frage", "Kam eine Antwort an?"],
        "policy": "Read-only. Use for questions about recent/completed answers, including whether a parent notification was recorded.",
    },
    {
        "operation": "report",
        "tool": "learnbuddy_parent_report",
        "examples": ["Bericht", "Wie lief es heute?", "Schick mir einen Report"],
        "notify_default": False,
        "policy": "Default notify=false. Set notify=true only when the parent explicitly asks to send/push the report.",
    },
    {
        "operation": "daily_status",
        "tool": "learnbuddy_daily_parent_status",
        "examples": ["Tagesstatus", "Schick den Tagesstatus", "Status heute Abend"],
        "notify_default": False,
        "policy_bounded": True,
        "policy": "One daily parent status. Respects pause-today and once-per-day guards; empty days are skipped unless include_empty=true.",
    },
    {
        "operation": "weekly_status",
        "tool": "learnbuddy_weekly_parent_status",
        "examples": ["Wochenbericht", "Schick den Wochenstatus", "Wie lief diese Woche?"],
        "notify_default": False,
        "policy_bounded": True,
        "policy": "One weekly parent report with compact recommendations. Respects pause-today and once-per-week guards; empty weeks are skipped unless include_empty=true.",
    },
    {
        "operation": "automation_control",
        "tool": "learnbuddy_parent_automation_control",
        "examples": ["heute pausieren", "Lernbot heute aus", "weiter", "Automatik wieder an"],
        "policy": "Only controls LearnBuddy parent-facing automation state; never changes child answers or external systems.",
    },
    {
        "operation": "resend_pending",
        "tool": "learnbuddy_deliver_pending_exercise",
        "examples": ["Nochmal senden", "Learner hat die Aufgabe nicht bekommen", "Schick die offene Aufgabe erneut"],
        "args": {"force": True},
        "policy": "Only resends the existing pending prompt. Does not create a new exercise or answer for the child.",
    },
    {
        "operation": "dispatch_plan",
        "tool": "learnbuddy_dispatch_plan",
        "examples": ["Starte den Lernplan", "Schick eine geplante Aufgabe", "Heute eine Mathe-Aufgabe aus dem Plan"],
        "policy_bounded": True,
        "policy": "Respects allowed_hours and existing pending sessions. Active learning plans guide automatic selection; daily_auto_limit gates generic automatic selection; explicit parent-scheduled due exercises dispatch after the current pending item clears.",
    },
    {
        "operation": "learning_plan",
        "tool": "learnbuddy_create_learning_plan / learnbuddy_learning_plan_status / learnbuddy_control_learning_plan",
        "examples": ["Erstelle einen Lernplan für Englisch", "Welcher Lernplan ist aktiv?", "Pausiere den Lernplan", "Lernplan beendet"],
        "policy_bounded": True,
        "policy": "Parent/admin only. Plans select from existing exercises by configured subject/focus and never generate unbounded child tasks by themselves.",
    },
    {
        "operation": "material_review",
        "tool": "learnbuddy_add_learning_material / learnbuddy_import_learning_material_file / learnbuddy_material_status / learnbuddy_approve_material_tasks",
        "examples": ["Ich habe ein Arbeitsblatt", "Importiere dieses Material", "Foto/PDF vom Arbeitsblatt hochladen", "Zeig die Material-Warteschlange", "Gib die ersten zwei Aufgaben mit Antworten 15 und 20 frei"],
        "requires": ["material_id", "expected_answers", "file_path"],
        "policy_bounded": True,
        "policy": "Parent/admin only. Pasted material and worksheet photos/PDFs become review state first; approval creates exercises only after ordered expected answers are supplied. Import/status never sends to the child.",
    },
    {
        "operation": "create_and_send_exercise",
        "tool": "learnbuddy_create_and_send_exercise",
        "examples": [
            "Schick Learner: Was ist 100 + 101?",
            "Gib Learner eine Matheaufgabe mit Antwort 201",
            "Frage Learner folgende Aufgaben",
        ],
        "requires": ["prompt", "answer_or_expected_answers"],
        "policy": "Use only when the parent provides or the agent deterministically verifies a concrete child-facing prompt plus expected answer(s) before sending.",
    },
    {
        "operation": "schedule_exercise",
        "tool": "learnbuddy_schedule_exercise",
        "examples": ["Schick Learner um 10:30: Was ist 10 + 20?", "Plane für morgen 16:00 eine Matheaufgabe mit Antwort 30"],
        "requires": ["prompt", "answer_or_expected_answers", "due_at"],
        "policy": "Creates a concrete one-shot exercise for later delivery. A dispatcher timer must run learnbuddy_dispatch_plan; scheduling alone does not prove child-visible delivery.",
    },
]

COMMON_PROPERTIES: dict[str, Any] = {
    "config_path": {"type": "string", "description": "Optional LearnBuddy YAML path. Usually omitted; gateway uses LEARNBUDDY_CONFIG_PATH."},
    "env_file": {"type": "string", "description": "Optional env file with delivery secrets. Usually omitted; gateway uses LEARNBUDDY_ENV_FILE."},
    "data_dir": {"type": "string", "description": "Optional runtime data dir override for tests or isolated demos."},
}

EXERCISE_PROPERTIES: dict[str, Any] = {
    **COMMON_PROPERTIES,
    "subject": {"type": "string", "enum": ["math", "german", "english", "general"], "default": "general"},
    "type": {"type": "string", "default": "short", "description": "Exercise type; keep short/question-answer for the alpha gateway."},
    "prompt": {"type": "string", "description": "Child-facing exercise prompt to send."},
    "answer": {"type": "string", "description": "Canonical expected answer. Required unless expected_answers is provided."},
    "expected_answers": {"type": "array", "items": {"type": "string"}, "description": "Alternative accepted answers."},
    "aliases": {"type": "array", "items": {"type": "string"}, "description": "Extra accepted aliases."},
    "difficulty": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Optional rough difficulty from 1 easy to 5 hard."},
    "topic": {"type": "string", "description": "Optional short topic label."},
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "learnbuddy_queue_exercise": {
        "type": "object",
        "properties": EXERCISE_PROPERTIES,
        "required": ["prompt"],
        "additionalProperties": False,
    },
    "learnbuddy_next_exercise": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "exercise_id": {"type": "string", "description": "Specific exercise id to open; omit to pick the next by subject."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"]},
            "mode": {"type": "string", "enum": ["manual", "auto"], "default": "manual"},
            "requested_by": {"type": "string", "enum": ["parent", "child", "system"], "default": "parent"},
            "deliver": {"type": "boolean", "default": False, "description": "Send opened prompt to the child delivery adapter."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_create_and_send_exercise": {
        "type": "object",
        "properties": {**EXERCISE_PROPERTIES, "deliver": {"type": "boolean", "default": True}},
        "required": ["prompt"],
        "anyOf": [{"required": ["answer"]}, {"required": ["expected_answers"]}],
        "additionalProperties": False,
    },
    "learnbuddy_schedule_exercise": {
        "type": "object",
        "properties": {
            **EXERCISE_PROPERTIES,
            "due_at": {"type": "string", "description": "ISO timestamp when dispatch-plan may deliver the exercise, e.g. 2026-05-28T10:30:00+02:00."},
        },
        "required": ["prompt", "due_at"],
        "anyOf": [{"required": ["answer"]}, {"required": ["expected_answers"]}],
        "additionalProperties": False,
    },
    "learnbuddy_deliver_pending_exercise": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "force": {"type": "boolean", "default": False, "description": "Send again even when the pending exercise is already marked delivered."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_dispatch_plan": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "exercise_id": {"type": "string", "description": "Specific exercise id to dispatch; omit to pick the next matching subject."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"]},
            "now": {"type": "string", "description": "Optional ISO timestamp override for tests or controlled scheduler runs."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_parent_command_contracts": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
        "additionalProperties": False,
    },
    "learnbuddy_create_learning_plan": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "title": {"type": "string", "description": "Parent-facing title for the learning plan."},
            "subjects": {"type": "array", "items": {"type": "string", "enum": ["math", "german", "english", "general"]}, "description": "Subjects the plan may dispatch from existing exercises."},
            "focus": {"type": "array", "items": {"type": "string"}, "description": "Optional short focus/topic labels."},
            "daily_goal": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
            "created_by": {"type": "string", "enum": ["parent", "system"], "default": "parent"},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    "learnbuddy_learning_plan_status": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
        "additionalProperties": False,
    },
    "learnbuddy_control_learning_plan": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "action": {"type": "string", "enum": ["pause", "resume", "complete", "cancel"], "description": "Control the active or selected learning plan."},
            "plan_id": {"type": "string", "description": "Specific plan id; defaults to the active plan."},
            "reason": {"type": "string", "description": "Optional short parent-facing reason."},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    "learnbuddy_add_learning_material": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "title": {"type": "string", "description": "Parent-facing title for the reviewed material."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"], "default": "general"},
            "source_type": {"type": "string", "enum": ["text", "image", "pdf", "unknown"], "default": "text"},
            "text_excerpt": {"type": "string", "description": "Public-safe extracted/pasted material text. Do not include secrets or private chat logs."},
            "task_candidates": {"type": "array", "items": {"type": "string"}, "description": "Reviewable candidate prompts extracted from the material."},
            "notes": {"type": "string", "description": "Short parent/admin note."},
        },
        "required": ["title", "text_excerpt"],
        "additionalProperties": False,
    },
    "learnbuddy_import_learning_material_file": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "title": {"type": "string", "description": "Parent-facing title for the reviewed file material."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"], "default": "general"},
            "file_path": {"type": "string", "description": "Local path to a parent-supplied worksheet photo, PDF, or text file cached on the gateway host."},
            "ocr_command": {"type": "string", "description": "Optional OCR/vision command for image files. Receives file_path as final argv item; LEARNBUDDY_MATERIAL_OCR_COMMAND can be used instead."},
            "max_bytes": {"type": "integer", "minimum": 1, "default": 8388608, "description": "Maximum accepted file size before extraction."},
            "notes": {"type": "string", "description": "Short parent/admin note."},
        },
        "required": ["title", "file_path"],
        "additionalProperties": False,
    },
    "learnbuddy_material_status": {
        "type": "object",
        "properties": {**COMMON_PROPERTIES, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}},
        "additionalProperties": False,
    },
    "learnbuddy_approve_material_tasks": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "material_id": {"type": "string", "description": "Material set id returned by learnbuddy_add_learning_material."},
            "expected_answers": {"type": "array", "items": {"type": "string"}, "description": "Ordered answers, one per approved task candidate."},
            "selected_indices": {"type": "array", "items": {"type": "integer"}, "description": "Optional zero-based candidate indices to approve."},
        },
        "required": ["material_id", "expected_answers"],
        "additionalProperties": False,
    },
    "learnbuddy_submit_answer": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "answer": {"type": "string", "description": "Answer text to evaluate for the currently pending exercise."},
            "input_mode": {"type": "string", "enum": ["text", "audio"], "default": "text"},
        },
        "required": ["answer"],
        "additionalProperties": False,
    },
    "learnbuddy_learning_status": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
        "additionalProperties": False,
    },
    "learnbuddy_parent_answer_status": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3, "description": "Number of recent answer records to include."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_parent_report": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "notify": {"type": "boolean", "default": False, "description": "Send the report to the configured parent adapter when true."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_daily_parent_status": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "notify": {"type": "boolean", "default": False, "description": "Send the daily status to the configured parent adapter when true."},
            "include_empty": {"type": "boolean", "default": False, "description": "Send even when no answers were recorded for the local day."},
            "force": {"type": "boolean", "default": False, "description": "Ignore the once-per-day send guard."},
            "now": {"type": "string", "description": "Optional ISO timestamp override for tests or controlled scheduler runs."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_weekly_parent_status": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "notify": {"type": "boolean", "default": False, "description": "Send the weekly report to the configured parent adapter when true."},
            "include_empty": {"type": "boolean", "default": False, "description": "Send even when no sessions or answers were recorded for the local week."},
            "force": {"type": "boolean", "default": False, "description": "Ignore the once-per-week send guard."},
            "now": {"type": "string", "description": "Optional ISO timestamp override for tests or controlled scheduler runs."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_parent_automation_control": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "action": {"type": "string", "enum": ["status", "pause_today", "resume"], "description": "Inspect, pause today's scheduled automation, or resume it."},
            "reason": {"type": "string", "description": "Optional short reason for pausing today."},
            "now": {"type": "string", "description": "Optional ISO timestamp override for tests or controlled scheduler runs."},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    "learnbuddy_parent_help_request": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "reason": {"type": "string", "description": "Short parent-facing reason why the learner needs help."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"]},
            "target": {"type": "string", "enum": ["parents", "primary_parent"], "default": "parents"},
            "urgent": {"type": "boolean", "default": False},
            "requested_by": {"type": "string", "enum": ["child", "parent", "system"], "default": "child"},
            "notify": {"type": "boolean", "default": False, "description": "Send the help request to the configured parent adapter when true."},
        },
        "required": ["reason"],
        "additionalProperties": False,
    },
    "learnbuddy_child_submit_answer": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "answer": {"type": "string", "description": "Child answer text for the currently pending exercise."},
            "input_mode": {"type": "string", "enum": ["text", "audio"], "default": "text"},
            "notify_parent": {"type": "boolean", "default": True, "description": "Notify the configured parent adapter about the answer result. Default true for child profiles."},
        },
        "required": ["answer"],
        "additionalProperties": False,
    },
    "learnbuddy_child_status": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
        "additionalProperties": False,
    },
    "learnbuddy_child_repeat_pending": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
        "additionalProperties": False,
    },
    "learnbuddy_child_request_next_exercise": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "request": {"type": "string", "default": "Noch eine", "description": "Original child text asking for another exercise."},
            "now": {"type": "string", "description": "Optional ISO timestamp override for policy-bound tests."},
            "notify_parent": {"type": "boolean", "default": True, "description": "Notify the configured parent adapter if policy/storage blocks the request."},
        },
        "additionalProperties": False,
    },
    "learnbuddy_child_request_parent_help": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "reason": {"type": "string", "description": "Short parent-facing reason why the learner needs help."},
            "subject": {"type": "string", "enum": ["math", "german", "english", "general"]},
            "urgent": {"type": "boolean", "default": False},
        },
        "required": ["reason"],
        "additionalProperties": False,
    },
}


def _load_env_file(args: dict[str, Any] | None = None) -> None:
    """Load optional LearnBuddy env vars before delivery/config operations.

    Existing process environment values win. The file is line-based KEY=VALUE,
    intentionally tiny so deployments do not need python-dotenv.
    """
    args = args or {}
    env_path = args.get("env_file") or os.getenv("LEARNBUDDY_ENV_FILE")
    if not env_path:
        return
    path = Path(str(env_path)).expanduser()
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _config(args: dict[str, Any] | None = None) -> LearnBuddyConfig:
    args = args or {}
    _load_env_file(args)
    config_path = args.get("config_path") or os.getenv("LEARNBUDDY_CONFIG_PATH")
    return LearnBuddyConfig.from_yaml(config_path) if config_path else LearnBuddyConfig()


def _runtime(args: dict[str, Any] | None = None) -> LearnBuddyRuntime:
    args = args or {}
    config = _config(args)
    data_dir = Path(args.get("data_dir") or config.resolved_storage_dir())
    max_attempts = int(args.get("max_attempts") or config.max_attempts)
    queue_max = int(args.get("queue_max") or config.queue_max)
    child_id = str(args.get("child_id") or config.child_id)
    child_name = str(args.get("child_name") or config.child_name)
    agent_name = str(args.get("agent_name") or config.agent_name)
    return LearnBuddyRuntime(
        data_dir,
        max_attempts=max_attempts,
        queue_max=queue_max,
        child_id=child_id,
        child_name=child_name,
        agent_name=agent_name,
    )


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _delivery_adapter(config: LearnBuddyConfig, *, recipient: str = "child"):
    return delivery_adapter_from_config(config, recipient=recipient)


def _delivery_succeeded(status: Any) -> bool:
    return str(status or "") in {"sent", "dry_run"}


def _deliver_pending_child_prompt(config: LearnBuddyConfig, runtime: LearnBuddyRuntime, *, force: bool = False) -> dict[str, Any]:
    state = runtime.status()
    pending = state.get("pending")
    if not isinstance(pending, dict):
        return {"status": "no_pending", "delivery": None, "session": None}
    child_delivery = pending.get("delivery", {}).get("child", {}) if isinstance(pending.get("delivery"), dict) else {}
    if _delivery_succeeded(child_delivery.get("status")) and not force:
        return {"status": "already_sent", "delivery": child_delivery, "session": pending}
    delivery = _delivery_adapter(config, recipient="child").deliver_child(
        DeliveryMessage(
            text=str(pending.get("prompt") or ""),
            metadata={"kind": "pending_exercise", "session_id": pending.get("id")},
        )
    )
    delivery_dict = delivery.to_dict()
    updated = runtime.mark_pending_delivery(delivery_dict)
    return {
        "status": "sent" if _delivery_succeeded(delivery_dict.get("status")) else delivery_dict.get("status", "error"),
        "delivery": delivery_dict,
        "session": updated,
    }


def learnbuddy_queue_exercise(args: dict[str, Any] | None = None) -> str:
    """Create a synthetic/manual exercise in the configured LearnBuddy store."""
    args = dict(args or {})
    runtime = _runtime(args)
    exercise = runtime.add_exercise({
        "subject": args.get("subject", "general"),
        "type": args.get("type", "short"),
        "prompt": args["prompt"],
        "answer": args.get("answer"),
        "expected_answers": args.get("expected_answers"),
        "aliases": args.get("aliases"),
        "difficulty": args.get("difficulty"),
        "topic": args.get("topic"),
    })
    return _json({"status": "created", "exercise": exercise})


def learnbuddy_next_exercise(args: dict[str, Any] | None = None) -> str:
    """Open the next matching exercise or queue it if another is pending."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    result = runtime.open_exercise(
        args.get("exercise_id"),
        subject=args.get("subject"),
        mode=args.get("mode", "manual"),
        requested_by=args.get("requested_by", "parent"),
    )
    if args.get("deliver") and result.get("status") == "opened":
        delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
        result["delivery"] = delivery_result.get("delivery")
        result["delivery_status"] = delivery_result.get("status")
        result["session"] = delivery_result.get("session") or result.get("session")
    return _json(result)


def learnbuddy_deliver_pending_exercise(args: dict[str, Any] | None = None) -> str:
    """Send or repair delivery of the currently pending child prompt."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    return _json(_deliver_pending_child_prompt(config, runtime, force=bool(args.get("force", False))))


def learnbuddy_schedule_exercise(args: dict[str, Any] | None = None) -> str:
    """Parent UX: create a concrete one-shot exercise for later dispatcher delivery."""
    args = dict(args or {})
    if not _has_expected_answer(args):
        return _json({
            "status": "missing_expected_answer",
            "error": "learnbuddy_schedule_exercise requires answer or expected_answers before scheduling a child-facing exercise.",
        })
    if not args.get("due_at"):
        return _json({"status": "missing_due_at", "error": "learnbuddy_schedule_exercise requires due_at."})
    runtime = _runtime(args)
    result = runtime.schedule_exercise({
        "subject": args.get("subject", "general"),
        "type": args.get("type", "short"),
        "prompt": args["prompt"],
        "answer": args.get("answer"),
        "expected_answers": args.get("expected_answers"),
        "aliases": args.get("aliases"),
        "difficulty": args.get("difficulty"),
        "topic": args.get("topic"),
    }, due_at=str(args.get("due_at")))
    return _json({"status": "scheduled", **result})


def learnbuddy_dispatch_plan(args: dict[str, Any] | None = None) -> str:
    """Open and deliver one automatic exercise when schedule policy allows it."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    now = _parse_datetime(args.get("now"), config.timezone)
    if not _inside_allowed_hours(now, config.allowed_hours_from, config.allowed_hours_to):
        return _json({
            "status": "outside_allowed_hours",
            "now": now.isoformat(),
            "allowed_hours": {"from": config.allowed_hours_from, "to": config.allowed_hours_to},
        })
    state = runtime.status()
    if isinstance(state.get("pending"), dict):
        return _json({"status": "pending_exists", "pending": state.get("pending")})
    scheduled = None
    if not args.get("exercise_id") and not args.get("subject"):
        scheduled = runtime.next_due_scheduled_exercise(now=now.isoformat(), timezone_name=config.timezone)
        if scheduled is None and runtime.pending_scheduled_exercises():
            return _json({"status": "no_due_scheduled_exercise", "now": now.isoformat()})
    if scheduled is None and not args.get("exercise_id") and not args.get("subject") and runtime.active_learning_plan():
        result = runtime.dispatch_learning_plan(now=now.isoformat(), timezone_name=config.timezone)
        if result.get("status") == "opened":
            delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
            result["delivery"] = delivery_result.get("delivery")
            result["delivery_status"] = delivery_result.get("status")
            result["session"] = delivery_result.get("session") or result.get("session")
        return _json(result)
    auto_count = _auto_sessions_today(runtime, now, config.timezone)
    if scheduled is None and auto_count >= config.daily_auto_limit:
        return _json({"status": "daily_limit_reached", "daily_auto_limit": config.daily_auto_limit, "auto_sessions_today": auto_count})
    try:
        result = runtime.open_exercise(
            args.get("exercise_id") or (str(scheduled.get("exercise_id")) if isinstance(scheduled, dict) else None),
            subject=args.get("subject"),
            mode="auto",
            requested_by="system",
            timestamp=now.astimezone(ZoneInfo("UTC")).isoformat(),
            source="scheduled_exercise" if scheduled else None,
            scheduled_id=str(scheduled.get("id")) if isinstance(scheduled, dict) else None,
        )
    except KeyError as exc:
        return _json({"status": "no_matching_exercise", "error": str(exc)})
    if result.get("status") == "opened":
        delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
        result["delivery"] = delivery_result.get("delivery")
        result["delivery_status"] = delivery_result.get("status")
        result["session"] = delivery_result.get("session") or result.get("session")
        if scheduled:
            result["scheduled"] = runtime.mark_scheduled_exercise_dispatched(
                str(scheduled.get("id")),
                session_id=(result.get("session") or {}).get("id") if isinstance(result.get("session"), dict) else None,
                delivery_result=delivery_result.get("delivery"),
            )
    return _json(result)


def _has_expected_answer(args: dict[str, Any]) -> bool:
    if args.get("answer") not in (None, ""):
        return True
    expected = args.get("expected_answers")
    if isinstance(expected, list):
        return any(str(item).strip() for item in expected if item is not None)
    return False


def learnbuddy_create_and_send_exercise(args: dict[str, Any] | None = None) -> str:
    """Create an exercise, open it immediately, and deliver it to the child adapter."""
    args = dict(args or {})
    if not _has_expected_answer(args):
        return _json({
            "status": "missing_expected_answer",
            "error": "learnbuddy_create_and_send_exercise requires answer or expected_answers before sending a child-facing exercise.",
        })
    runtime = _runtime(args)
    state = runtime.status()
    queue_value = state.get("queue")
    queue = queue_value if isinstance(queue_value, list) else []
    if isinstance(state.get("pending"), dict) and len(queue) >= runtime.queue_max:
        return _json({
            "status": "queue_full",
            "error": "LearnBuddy already has one open exercise and the follow-up queue is full; no new exercise was stored or delivered.",
            "pending": state.get("pending"),
            "queue_count": len(queue),
            "queue_max": runtime.queue_max,
        })
    queued = json.loads(learnbuddy_queue_exercise(args))
    exercise = queued["exercise"]
    next_args = dict(args)
    next_args["exercise_id"] = exercise["id"]
    next_args["deliver"] = args.get("deliver", True)
    opened = json.loads(learnbuddy_next_exercise(next_args))
    status = "sent" if opened.get("delivery", {}).get("status") in {"sent", "dry_run"} else opened.get("status", "created")
    return _json({"status": status, "exercise": exercise, "opened": opened})


def learnbuddy_parent_command_contracts(args: dict[str, Any] | None = None) -> str:
    """Return the supported Parent Telegram command contracts for gateway routing."""
    _config(dict(args or {}))
    return _json({
        "status": "ok",
        "audience": "parent_telegram",
        "contracts": PARENT_COMMAND_CONTRACTS,
        "safety": {
            "no_child_toolset": True,
            "no_unbounded_generation": True,
            "delivery_state_required": True,
            "parent_initiated_push_requires_explicit_request": True,
            "child_answer_notifications_may_be_automatic": True,
        },
    })


def learnbuddy_add_learning_material(args: dict[str, Any] | None = None) -> str:
    """Store parent-supplied learning material for review without child delivery."""
    args = dict(args or {})
    runtime = _runtime(args)
    material = runtime.add_material_set({
        "title": args.get("title"),
        "subject": args.get("subject", "general"),
        "source_type": args.get("source_type", "text"),
        "text_excerpt": args.get("text_excerpt") or args.get("text") or "",
        "task_candidates": args.get("task_candidates") or [],
        "notes": args.get("notes") or "",
    })
    return _json({"status": material["status"], "material": material})


def learnbuddy_import_learning_material_file(args: dict[str, Any] | None = None) -> str:
    """Extract parent-supplied local file material into review state without child delivery."""
    args = dict(args or {})
    runtime = _runtime(args)
    import_result = build_material_from_file(
        args.get("file_path") or "",
        title=str(args.get("title") or ""),
        subject=str(args.get("subject") or "general"),
        notes=str(args.get("notes") or ""),
        ocr_command=args.get("ocr_command") or os.getenv("LEARNBUDDY_MATERIAL_OCR_COMMAND"),
        max_bytes=int(args.get("max_bytes") or 8 * 1024 * 1024),
    )
    if import_result.get("status") != "ok":
        return _json(import_result)
    material = runtime.add_material_set(import_result["material"])
    return _json({
        "status": material["status"],
        "material": material,
        "extraction": import_result.get("extraction"),
        "preview": import_result.get("preview"),
    })


def learnbuddy_material_status(args: dict[str, Any] | None = None) -> str:
    """Return the parent/admin material review queue."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.material_status(limit=int(args.get("limit") or 10)))


def learnbuddy_approve_material_tasks(args: dict[str, Any] | None = None) -> str:
    """Convert reviewed material candidates into bounded exercises after parent-provided answers."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.approve_material_tasks(
        str(args.get("material_id") or ""),
        expected_answers=args.get("expected_answers") or [],
        selected_indices=args.get("selected_indices"),
        requested_by="parent",
    ))


def learnbuddy_create_learning_plan(args: dict[str, Any] | None = None) -> str:
    """Create and activate a bounded parent-approved learning plan."""
    args = dict(args or {})
    runtime = _runtime(args)
    plan = runtime.create_learning_plan({
        "title": args.get("title"),
        "subjects": args.get("subjects") or [],
        "focus": args.get("focus") or [],
        "daily_goal": args.get("daily_goal") or 1,
        "created_by": args.get("created_by") or "parent",
    })
    return _json({"status": plan["status"], "plan": plan})


def learnbuddy_learning_plan_status(args: dict[str, Any] | None = None) -> str:
    """Return active and historical learning plans."""
    runtime = _runtime(dict(args or {}))
    return _json(runtime.learning_plan_status())


def learnbuddy_control_learning_plan(args: dict[str, Any] | None = None) -> str:
    """Pause, resume, complete, or cancel the active/selected learning plan."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.set_learning_plan(str(args.get("action") or ""), plan_id=args.get("plan_id"), reason=args.get("reason")))


def learnbuddy_submit_answer(args: dict[str, Any] | None = None) -> str:
    """Evaluate an answer for the currently pending exercise."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.submit_answer(args.get("answer", ""), input_mode=args.get("input_mode", "text")))


def learnbuddy_learning_status(args: dict[str, Any] | None = None) -> str:
    """Return current pending/queue status."""
    runtime = _runtime(dict(args or {}))
    return _json(runtime.status())


def learnbuddy_parent_answer_status(args: dict[str, Any] | None = None) -> str:
    """Return recent answer status for parent questions about completed/recent answers."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.parent_answer_status(limit=int(args.get("limit") or 3)))


def learnbuddy_parent_report(args: dict[str, Any] | None = None) -> str:
    """Render a simple parent-facing report from local synthetic data."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    report = runtime.parent_report()
    if args.get("notify"):
        report["notification"] = ParentNotifier(_delivery_adapter(config, recipient="parent")).notify_report(report).to_dict()
    return _json(report)


def learnbuddy_daily_parent_status(args: dict[str, Any] | None = None) -> str:
    """Render/send one daily parent status with pause and duplicate guards."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    return _json(run_daily_parent_status(
        config,
        runtime,
        notify=bool(args.get("notify", False)),
        include_empty=bool(args.get("include_empty", False)),
        force=bool(args.get("force", False)),
        now=args.get("now"),
    ))


def learnbuddy_weekly_parent_status(args: dict[str, Any] | None = None) -> str:
    """Render/send one weekly parent report with recommendations and duplicate guards."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    return _json(run_weekly_parent_status(
        config,
        runtime,
        notify=bool(args.get("notify", False)),
        include_empty=bool(args.get("include_empty", False)),
        force=bool(args.get("force", False)),
        now=args.get("now"),
    ))


def learnbuddy_parent_automation_control(args: dict[str, Any] | None = None) -> str:
    """Inspect, pause, or resume parent-facing scheduled automation."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    return _json(runtime.set_parent_automation(
        str(args.get("action") or "status"),
        now=args.get("now"),
        timezone_name=config.timezone,
        reason=args.get("reason"),
    ))


def learnbuddy_parent_help_request(args: dict[str, Any] | None = None) -> str:
    """Record a bounded request for parent help; notify only when requested."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    request = runtime.create_parent_help_request(
        args.get("reason", ""),
        subject=args.get("subject"),
        target=args.get("target", "parents"),
        urgent=bool(args.get("urgent", False)),
        requested_by=args.get("requested_by", "child"),
    )
    if args.get("notify"):
        request["notification"] = ParentNotifier(_delivery_adapter(config, recipient="parent")).notify_help_request(request).to_dict()
    return _json({"status": "created", "help_request": request})


def learnbuddy_child_submit_answer(args: dict[str, Any] | None = None) -> str:
    """Child profile: submit an answer, return child feedback, and notify the parent adapter by default."""
    child_args = dict(args or {})
    config = _config(child_args)
    runtime = _runtime(child_args)
    pending = runtime.status().get("pending")
    result = runtime.submit_answer(child_args.get("answer", ""), input_mode=child_args.get("input_mode", "text"))
    if child_args.get("notify_parent", True) and isinstance(pending, dict) and result.get("result") != "no_pending":
        prompt = str(pending.get("prompt") or "die offene Aufgabe")
        answer_text = str(child_args.get("answer", ""))
        status = "richtig" if result.get("correct") else "noch nicht richtig"
        if result.get("result") == "exhausted":
            status = "alle Versuche aufgebraucht"
        attempts = result.get("attempts")
        max_attempts = result.get("max_attempts")
        parent_text = (
            f"📚 {config.agent_name}: {config.child_name} hat geantwortet in {pending.get('subject', 'general')}\n"
            f"Aufgabe: {prompt}\n"
            f"Antwort: {answer_text}\n"
            f"Ergebnis: {status}, Versuch {attempts}/{max_attempts}."
        )
        parent_delivery = _delivery_adapter(config, recipient="parent").deliver_parent(
            DeliveryMessage(text=parent_text, metadata={"kind": "child_answer_result", "session_id": pending.get("id")})
        ).to_dict()
        result["parent_delivery"] = parent_delivery
        runtime.record_answer_parent_delivery(str(pending.get("id") or ""), parent_delivery)
    return _json(result)


def learnbuddy_child_status(args: dict[str, Any] | None = None) -> str:
    """Child-profile alias: return only the bounded LearnBuddy status."""
    return learnbuddy_learning_status(args)


def learnbuddy_child_repeat_pending(args: dict[str, Any] | None = None) -> str:
    """Child profile: resend the current pending prompt without incrementing attempts."""
    child_args = dict(args or {})
    config = _config(child_args)
    runtime = _runtime(child_args)
    pending = runtime.status().get("pending")
    if not isinstance(pending, dict):
        return _json({"command": "repeat", "status": "no_pending", "child_delivery": None})
    metadata = {"kind": "pending_exercise_repeat", "session_id": pending.get("id")}
    text = f"Hier ist die Aufgabe nochmal:\n{pending.get('prompt')}"
    child_delivery = _with_metadata(
        _delivery_adapter(config, recipient="child").deliver_child(DeliveryMessage(text=text, metadata=metadata)).to_dict(),
        metadata,
        text=text,
    )
    if child_delivery is not None:
        runtime.mark_pending_delivery(child_delivery)
    return _json({
        "command": "repeat",
        "status": "sent" if _delivery_succeeded(child_delivery.get("status") if child_delivery else None) else (child_delivery or {}).get("status", "error"),
        "child_delivery": child_delivery,
    })


def learnbuddy_child_request_next_exercise(args: dict[str, Any] | None = None) -> str:
    """Child profile: policy-bound request for exactly one next exercise."""
    child_args = dict(args or {})
    config = _config(child_args)
    runtime = _runtime(child_args)
    pending = runtime.status().get("pending")
    if isinstance(pending, dict):
        metadata = {"kind": "finish_pending_first", "session_id": pending.get("id")}
        text = f"Erst diese Aufgabe lösen, dann gibt’s die nächste:\n{pending.get('prompt')}"
        child_delivery = _with_metadata(
            _delivery_adapter(config, recipient="child").deliver_child(DeliveryMessage(text=text, metadata=metadata)).to_dict(),
            metadata,
            text=text,
        )
        return _json({
            "command": "next",
            "dispatch": {"status": "pending_exists", "pending": pending},
            "child_delivery": child_delivery,
            "parent_delivery": None,
        })

    dispatch, child_delivery, help_request, parent_delivery = _dispatch_child_requested_next_exercise(
        config,
        runtime,
        answer_text=str(child_args.get("request") or "Noch eine"),
        send_feedback=True,
        notify_parent=bool(child_args.get("notify_parent", True)),
        now=child_args.get("now"),
    )
    result: dict[str, Any] = {"command": "next", "dispatch": dispatch, "child_delivery": child_delivery, "parent_delivery": parent_delivery}
    if help_request is not None:
        result["help_request"] = help_request
    return _json(result)


def learnbuddy_child_request_parent_help(args: dict[str, Any] | None = None) -> str:
    """Child-profile alias: request parent help and notify the parent adapter."""
    child_args = dict(args or {})
    child_args["requested_by"] = "child"
    child_args["target"] = "parents"
    child_args["notify"] = True
    return learnbuddy_parent_help_request(child_args)


TOOLS = [
    ("learnbuddy_queue_exercise", learnbuddy_queue_exercise, "learnbuddy_learning", "Create a bounded LearnBuddy exercise for later use. Parent UX: use this only when the parent explicitly asks to queue, not send."),
    ("learnbuddy_next_exercise", learnbuddy_next_exercise, "learnbuddy_learning", "Open an existing LearnBuddy exercise. Set deliver=true only when the parent asked to send/open it now."),
    ("learnbuddy_create_and_send_exercise", learnbuddy_create_and_send_exercise, "learnbuddy_learning", "Parent UX one-shot: create a short exercise, open it, and deliver it to the child. Do not call without a concrete prompt and expected answer(s)."),
    ("learnbuddy_deliver_pending_exercise", learnbuddy_deliver_pending_exercise, "learnbuddy_learning", "Repair or resend the current pending prompt to the child. Use when a parent reports that the learner did not receive the task."),
    ("learnbuddy_schedule_exercise", learnbuddy_schedule_exercise, "learnbuddy_learning", "Parent UX one-shot scheduling: create a concrete exercise with an expected answer and due_at for later dispatcher delivery."),
    ("learnbuddy_dispatch_plan", learnbuddy_dispatch_plan, "learnbuddy_learning", "Scheduler-safe: open and deliver one due automatic LearnBuddy exercise when allowed-hours and daily-limit policy permit it."),
    ("learnbuddy_create_learning_plan", learnbuddy_create_learning_plan, "learnbuddy_learning", "Parent/admin: create and activate a bounded learning plan over existing exercises. Does not generate child tasks by itself."),
    ("learnbuddy_learning_plan_status", learnbuddy_learning_plan_status, "learnbuddy_learning", "Parent/admin: show the active learning plan and plan history."),
    ("learnbuddy_control_learning_plan", learnbuddy_control_learning_plan, "learnbuddy_learning", "Parent/admin: pause, resume, complete, or cancel the active learning plan."),
    ("learnbuddy_add_learning_material", learnbuddy_add_learning_material, "learnbuddy_learning", "Parent/admin: store parent-supplied worksheet/material text for review; no child delivery or exercise creation."),
    ("learnbuddy_import_learning_material_file", learnbuddy_import_learning_material_file, "learnbuddy_learning", "Parent/admin: extract a cached worksheet photo, PDF, or text file into material review state; no child delivery or exercise creation."),
    ("learnbuddy_material_status", learnbuddy_material_status, "learnbuddy_learning", "Parent/admin: show pending reviewed learning materials and approval state."),
    ("learnbuddy_approve_material_tasks", learnbuddy_approve_material_tasks, "learnbuddy_learning", "Parent/admin: convert reviewed material candidates into exercises only after ordered expected answers are provided."),
    ("learnbuddy_parent_command_contracts", learnbuddy_parent_command_contracts, "learnbuddy_learning", "Parent command contract reference for Telegram routing: status, report, resend pending, dispatch plan, and create/send exercise. Read before improvising ambiguous parent commands."),
    ("learnbuddy_submit_answer", learnbuddy_submit_answer, "learnbuddy_learning", "Submit an answer for the currently pending LearnBuddy exercise."),
    ("learnbuddy_learning_status", learnbuddy_learning_status, "learnbuddy_learning", "Show LearnBuddy current pending/queue status only; not answer history."),
    ("learnbuddy_parent_answer_status", learnbuddy_parent_answer_status, "learnbuddy_learning", "Show recent answer status for parents, including the latest prompt, answer result, and parent notification delivery record."),
    ("learnbuddy_parent_report", learnbuddy_parent_report, "learnbuddy_learning", "Summarize LearnBuddy progress for a parent; set notify=true only when the parent asked for a pushed report."),
    ("learnbuddy_daily_parent_status", learnbuddy_daily_parent_status, "learnbuddy_learning", "Scheduler-safe daily parent status: one local-day report with pause, duplicate, and empty-day guards."),
    ("learnbuddy_weekly_parent_status", learnbuddy_weekly_parent_status, "learnbuddy_learning", "Scheduler-safe weekly parent report: current-week summary, recommendations, pause, duplicate, and empty-week guards."),
    ("learnbuddy_parent_automation_control", learnbuddy_parent_automation_control, "learnbuddy_learning", "Inspect, pause today, or resume LearnBuddy parent-facing scheduled automation."),
    ("learnbuddy_parent_help_request", learnbuddy_parent_help_request, "learnbuddy_learning", "Create a bounded parent-help request. Notify parents only with notify=true; never use for external/non-learning actions."),
    ("learnbuddy_child_submit_answer", learnbuddy_child_submit_answer, "learnbuddy_child", "Child profile: submit an answer for the current LearnBuddy exercise. No file, terminal, or generic messaging access."),
    ("learnbuddy_child_status", learnbuddy_child_status, "learnbuddy_child", "Child profile: check whether a LearnBuddy exercise is pending."),
    ("learnbuddy_child_repeat_pending", learnbuddy_child_repeat_pending, "learnbuddy_child", "Child profile: resend the pending prompt without incrementing attempts."),
    ("learnbuddy_child_request_next_exercise", learnbuddy_child_request_next_exercise, "learnbuddy_child", "Child profile: policy-bound request for exactly one next exercise; respects pending state, allowed hours, and daily limits."),
    ("learnbuddy_child_request_parent_help", learnbuddy_child_request_parent_help, "learnbuddy_child", "Child profile: ask the configured parent for learning help. Use only for learning support, not external actions."),
]


def register(ctx):  # pragma: no cover - depends on Hermes plugin runtime
    """Register bounded tools with Hermes when loaded as a user plugin."""
    for name, handler, toolset, description in TOOLS:
        schema = {
            "name": name,
            "description": description,
            "parameters": TOOL_SCHEMAS[name],
        }
        ctx.register_tool(name=name, schema=schema, toolset=toolset, handler=lambda args, _handler=handler, **_: _handler(args))
    return None
