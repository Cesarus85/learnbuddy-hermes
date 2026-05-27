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

from learnbuddy_core.cli import _auto_sessions_today, _inside_allowed_hours, _parse_datetime
from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.delivery import DeliveryMessage, delivery_adapter_from_config
from learnbuddy_core.notifier import ParentNotifier
from learnbuddy_core.runtime import LearnBuddyRuntime

PLUGIN_NAME = "learnbuddy-learning"
PLUGIN_VERSION = "0.1.0-alpha.9"

PARENT_COMMAND_CONTRACTS: list[dict[str, Any]] = [
    {
        "operation": "status",
        "tool": "learnbuddy_learning_status",
        "examples": ["Status", "Was ist offen?", "Zeig die Queue", "Hat Learner gerade eine Aufgabe?"],
        "policy": "Read-only. Use for parent status questions; never sends Telegram messages.",
    },
    {
        "operation": "report",
        "tool": "learnbuddy_parent_report",
        "examples": ["Bericht", "Wie lief es heute?", "Schick mir einen Report"],
        "notify_default": False,
        "policy": "Default notify=false. Set notify=true only when the parent explicitly asks to send/push the report.",
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
        "policy": "Respects allowed_hours, daily_auto_limit, and existing pending sessions.",
    },
    {
        "operation": "create_and_send_exercise",
        "tool": "learnbuddy_create_and_send_exercise",
        "examples": ["Schick Learner: Was ist 100 + 101?", "Gib Learner eine Matheaufgabe mit Antwort 201"],
        "requires": ["prompt", "answer"],
        "policy": "Use only when the parent provides or approves a concrete child-facing prompt and expected answer.",
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
    "learnbuddy_parent_report": {
        "type": "object",
        "properties": {
            **COMMON_PROPERTIES,
            "notify": {"type": "boolean", "default": False, "description": "Send the report to the configured parent adapter when true."},
        },
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
        },
        "required": ["answer"],
        "additionalProperties": False,
    },
    "learnbuddy_child_status": {
        "type": "object",
        "properties": COMMON_PROPERTIES,
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
    child_id = str(args.get("child_id") or config.child_id)
    child_name = str(args.get("child_name") or config.child_name)
    agent_name = str(args.get("agent_name") or config.agent_name)
    return LearnBuddyRuntime(
        data_dir,
        max_attempts=max_attempts,
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
    auto_count = _auto_sessions_today(runtime, now, config.timezone)
    if auto_count >= config.daily_auto_limit:
        return _json({"status": "daily_limit_reached", "daily_auto_limit": config.daily_auto_limit, "auto_sessions_today": auto_count})
    try:
        result = runtime.open_exercise(
            args.get("exercise_id"),
            subject=args.get("subject"),
            mode="auto",
            requested_by="system",
            timestamp=now.astimezone(ZoneInfo("UTC")).isoformat(),
        )
    except KeyError as exc:
        return _json({"status": "no_matching_exercise", "error": str(exc)})
    if result.get("status") == "opened":
        delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
        result["delivery"] = delivery_result.get("delivery")
        result["delivery_status"] = delivery_result.get("status")
        result["session"] = delivery_result.get("session") or result.get("session")
    return _json(result)


def learnbuddy_create_and_send_exercise(args: dict[str, Any] | None = None) -> str:
    """Create an exercise, open it immediately, and deliver it to the child adapter."""
    args = dict(args or {})
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
            "notify_requires_explicit_parent_request": True,
        },
    })


def learnbuddy_submit_answer(args: dict[str, Any] | None = None) -> str:
    """Evaluate an answer for the currently pending exercise."""
    args = dict(args or {})
    runtime = _runtime(args)
    return _json(runtime.submit_answer(args.get("answer", ""), input_mode=args.get("input_mode", "text")))


def learnbuddy_learning_status(args: dict[str, Any] | None = None) -> str:
    """Return current pending/queue status."""
    runtime = _runtime(dict(args or {}))
    return _json(runtime.status())


def learnbuddy_parent_report(args: dict[str, Any] | None = None) -> str:
    """Render a simple parent-facing report from local synthetic data."""
    args = dict(args or {})
    config = _config(args)
    runtime = _runtime(args)
    report = runtime.parent_report()
    if args.get("notify"):
        report["notification"] = ParentNotifier(_delivery_adapter(config, recipient="parent")).notify_report(report).to_dict()
    return _json(report)


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
    """Child-profile alias: submit an answer for the current exercise."""
    return learnbuddy_submit_answer(args)


def learnbuddy_child_status(args: dict[str, Any] | None = None) -> str:
    """Child-profile alias: return only the bounded LearnBuddy status."""
    return learnbuddy_learning_status(args)


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
    ("learnbuddy_create_and_send_exercise", learnbuddy_create_and_send_exercise, "learnbuddy_learning", "Parent UX one-shot: create a short exercise, open it, and deliver it to the child. Do not call without a concrete prompt and expected answer."),
    ("learnbuddy_deliver_pending_exercise", learnbuddy_deliver_pending_exercise, "learnbuddy_learning", "Repair or resend the current pending prompt to the child. Use when a parent reports that the learner did not receive the task."),
    ("learnbuddy_dispatch_plan", learnbuddy_dispatch_plan, "learnbuddy_learning", "Scheduler-safe: open and deliver one due automatic LearnBuddy exercise when allowed-hours and daily-limit policy permit it."),
    ("learnbuddy_parent_command_contracts", learnbuddy_parent_command_contracts, "learnbuddy_learning", "Parent command contract reference for Telegram routing: status, report, resend pending, dispatch plan, and create/send exercise. Read before improvising ambiguous parent commands."),
    ("learnbuddy_submit_answer", learnbuddy_submit_answer, "learnbuddy_learning", "Submit an answer for the currently pending LearnBuddy exercise."),
    ("learnbuddy_learning_status", learnbuddy_learning_status, "learnbuddy_learning", "Show LearnBuddy pending/queue status."),
    ("learnbuddy_parent_report", learnbuddy_parent_report, "learnbuddy_learning", "Summarize LearnBuddy progress for a parent; set notify=true only when the parent asked for a pushed report."),
    ("learnbuddy_parent_help_request", learnbuddy_parent_help_request, "learnbuddy_learning", "Create a bounded parent-help request. Notify parents only with notify=true; never use for external/non-learning actions."),
    ("learnbuddy_child_submit_answer", learnbuddy_child_submit_answer, "learnbuddy_child", "Child profile: submit an answer for the current LearnBuddy exercise. No file, terminal, or generic messaging access."),
    ("learnbuddy_child_status", learnbuddy_child_status, "learnbuddy_child", "Child profile: check whether a LearnBuddy exercise is pending."),
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
