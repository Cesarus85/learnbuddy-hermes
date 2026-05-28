"""Public-safe LearnBuddy doctor checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .config import LearnBuddyConfig
from .delivery import delivery_adapter_from_config


def build_doctor_report(config: LearnBuddyConfig) -> dict[str, Any]:
    """Return a machine-readable doctor report without secret values."""
    checks = [
        {"name": "config", "status": "ok"},
        _storage_check(config),
        *_delivery_checks(config),
    ]
    overall = "error" if any(check["status"] == "error" for check in checks) else "ok"
    return {
        "overall": overall,
        "config": {
            "child_id": config.child_id,
            "child_name": config.child_name,
            "agent_name": config.agent_name,
            "max_attempts": config.max_attempts,
            "storage_dir": str(config.resolved_storage_dir()),
            "delivery_mode": config.delivery_mode,
        },
        "checks": checks,
    }


def doctor_exit_code(report: dict[str, Any]) -> int:
    return 0 if report.get("overall") == "ok" else 1


def format_text_report(report: dict[str, Any]) -> str:
    config = report["config"]
    lines = [
        "LearnBuddy doctor",
        f"child_id={config['child_id']}",
        f"child_name={config['child_name']}",
        f"agent_name={config['agent_name']}",
        f"max_attempts={config['max_attempts']}",
        f"storage_dir={config['storage_dir']}",
        f"delivery_mode={config['delivery_mode']}",
        f"overall={report['overall']}",
    ]
    lines.extend(_format_check(check) for check in report["checks"])
    return "\n".join(lines)


def _storage_check(config: LearnBuddyConfig) -> dict[str, Any]:
    storage = config.resolved_storage_dir()
    existing_ancestor = _nearest_existing_parent(storage)
    base_writable = os.access(existing_ancestor, os.W_OK)
    runtime_files = [
        "state.json",
        "exercises.jsonl",
        "sessions.jsonl",
        "answers.jsonl",
        "help_requests.jsonl",
        "scheduled_exercises.jsonl",
    ]
    unwritable_files = [name for name in runtime_files if (storage / name).exists() and not os.access(storage / name, os.W_OK)]
    writable = base_writable and not unwritable_files
    creatable = not storage.exists() and base_writable
    return {
        "name": "storage",
        "status": "ok" if writable else "error",
        "path": str(storage),
        "exists": storage.exists(),
        "parent_exists": storage.parent.exists(),
        "parent_writable": os.access(storage.parent, os.W_OK) if storage.parent.exists() else False,
        "creatable": creatable,
        "unwritable_files": unwritable_files,
    }


def _nearest_existing_parent(path: Path) -> Path:
    current = path if path.exists() else path.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _delivery_checks(config: LearnBuddyConfig) -> list[dict[str, Any]]:
    mode = str(config.delivery_mode)
    if mode == "dry_run":
        return [{"name": "delivery", "status": "ok", "mode": mode}]
    if mode != "telegram":
        try:
            delivery_adapter_from_config(config)
        except ValueError as exc:
            return [{"name": "delivery", "status": "error", "mode": mode, "error": str(exc)}]
        return [{"name": "delivery", "status": "ok", "mode": mode}]
    return [
        _telegram_env_check("delivery_child", config.child_telegram_bot_token_env, config.child_telegram_chat_id_env),
        _telegram_env_check("delivery_parent", config.parent_telegram_bot_token_env, config.parent_telegram_chat_id_env),
    ]


def _telegram_env_check(name: str, token_env: str, chat_env: str) -> dict[str, Any]:
    missing = [env_name for env_name in [token_env, chat_env] if not os.getenv(env_name)]
    check: dict[str, Any] = {
        "name": name,
        "status": "error" if missing else "ok",
        "mode": "telegram",
        "token_env": token_env,
        "chat_id_env": chat_env,
    }
    if missing:
        check["missing"] = missing
    return check


def _format_check(check: dict[str, Any]) -> str:
    fields: list[str] = [f"check={check['name']}", f"status={check['status']}"]
    for key in ["missing", "mode", "path", "exists", "parent_exists", "parent_writable", "creatable", "unwritable_files", "error"]:
        if key not in check:
            continue
        value = check[key]
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        fields.append(f"{key}={value}")
    return " ".join(fields)
