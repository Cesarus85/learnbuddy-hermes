"""Hermes plugin entrypoint for LearnBuddy.

Only generic, tested LearnBuddy core pieces live here. Production family-specific
plugins must not be copied into this repository.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.delivery import DeliveryMessage, delivery_adapter_from_config
from learnbuddy_core.runtime import LearnBuddyRuntime

PLUGIN_NAME = "learnbuddy-learning"
PLUGIN_VERSION = "0.1.0-alpha.0"


def _config(args: dict[str, Any] | None = None) -> LearnBuddyConfig:
    args = args or {}
    return LearnBuddyConfig.from_yaml(args["config_path"]) if args.get("config_path") else LearnBuddyConfig()


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


def _delivery_adapter(config: LearnBuddyConfig):
    return delivery_adapter_from_config(config)


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
        delivery = _delivery_adapter(config).deliver_child(
            DeliveryMessage(
                text=str(result.get("prompt") or ""),
                metadata={"session_id": result.get("session", {}).get("id")},
            )
        )
        result["delivery"] = delivery.to_dict()
    return _json(result)


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
    runtime = _runtime(dict(args or {}))
    return _json(runtime.parent_report())


TOOLS = [
    ("learnbuddy_queue_exercise", learnbuddy_queue_exercise, "Create a bounded LearnBuddy exercise."),
    ("learnbuddy_next_exercise", learnbuddy_next_exercise, "Open or queue the next LearnBuddy exercise."),
    ("learnbuddy_submit_answer", learnbuddy_submit_answer, "Submit an answer for the pending LearnBuddy exercise."),
    ("learnbuddy_learning_status", learnbuddy_learning_status, "Show LearnBuddy pending/queue status."),
    ("learnbuddy_parent_report", learnbuddy_parent_report, "Summarize LearnBuddy progress for a parent."),
]


def register(ctx):  # pragma: no cover - depends on Hermes plugin runtime
    """Register bounded tools with Hermes when loaded as a user plugin."""
    for name, handler, description in TOOLS:
        schema = {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        }
        ctx.register_tool(name=name, schema=schema, toolset="learnbuddy_learning", handler=lambda args, _handler=handler, **_: _handler(args))
    return None
