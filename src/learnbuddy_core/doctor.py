"""Public-safe LearnBuddy doctor checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import yaml

from .config import LearnBuddyConfig
from .delivery import delivery_adapter_from_config


FORBIDDEN_CHILD_TOOLSETS = {
    "terminal",
    "file",
    "code_execution",
    "homeassistant",
    "messaging",
}


def build_doctor_report(
    config: LearnBuddyConfig,
    *,
    hermes_home: str | Path | None = None,
    parent_profile: str | None = None,
    child_profile: str | None = None,
    systemd_user_dir: str | Path | None = None,
    child_gateway_service: str | None = None,
    dispatch_timer_profile: str | None = None,
) -> dict[str, Any]:
    """Return a machine-readable doctor report without secret values."""
    checks = [
        {"name": "config", "status": "ok"},
        _storage_check(config),
        *_delivery_checks(config),
    ]
    hermes_root = Path(hermes_home).expanduser() if hermes_home else Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
    unit_root = Path(systemd_user_dir).expanduser() if systemd_user_dir else Path("~/.config/systemd/user").expanduser()
    if parent_profile:
        checks.append(_profile_check(hermes_root, parent_profile, role="parent"))
    if child_profile:
        checks.append(_profile_check(hermes_root, child_profile, role="child"))
    if child_gateway_service:
        expected_profile = child_profile or child_gateway_service.removeprefix("hermes-gateway-")
        checks.append(_child_gateway_service_check(unit_root, child_gateway_service, expected_profile=expected_profile))
    if dispatch_timer_profile:
        checks.append(_dispatch_timer_check(unit_root, dispatch_timer_profile))
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


def _profile_home(hermes_home: Path, profile: str) -> Path:
    return hermes_home if profile == "default" else hermes_home / "profiles" / profile


def _profile_check(hermes_home: Path, profile: str, *, role: str) -> dict[str, Any]:
    profile_dir = _profile_home(hermes_home, profile)
    config_path = profile_dir / "config.yaml"
    env_path = profile_dir / ".env"
    plugin_yaml = profile_dir / "plugins" / "learnbuddy-learning" / "plugin.yaml"
    issues: list[str] = []
    if not profile_dir.exists():
        issues.append("missing_profile")
    if not (profile_dir / "SOUL.md").exists():
        issues.append("missing_soul")
    if not plugin_yaml.exists():
        issues.append("missing_plugin:learnbuddy-learning")
    config = _read_yaml_mapping(config_path)
    if config_path.exists() and not config:
        issues.append("empty_or_invalid_config")
    telegram_toolsets = _as_list(_mapping(config.get("platform_toolsets")).get("telegram"))
    known_toolsets = _as_list(_mapping(config.get("known_plugin_toolsets")).get("telegram"))
    disabled_toolsets = _as_list(_mapping(config.get("agent")).get("disabled_toolsets"))
    if role == "parent":
        _require_in("telegram_toolset", "learnbuddy_learning", telegram_toolsets, issues)
        _forbid_in("telegram_toolset", "learnbuddy_child", telegram_toolsets, issues)
        for toolset in ["learnbuddy_learning", "learnbuddy_child"]:
            _require_in("known_plugin_toolset", toolset, known_toolsets, issues)
        _require_in("disabled_toolset", "learnbuddy_child", disabled_toolsets, issues)
        required_env = {"LEARNBUDDY_CONFIG_PATH"}
    else:
        _require_in("telegram_toolset", "learnbuddy_child", telegram_toolsets, issues)
        _forbid_in("telegram_toolset", "learnbuddy_learning", telegram_toolsets, issues)
        for toolset in ["learnbuddy_child", "learnbuddy_learning"]:
            _require_in("known_plugin_toolset", toolset, known_toolsets, issues)
        for toolset in sorted(FORBIDDEN_CHILD_TOOLSETS):
            _require_in("disabled_toolset", toolset, disabled_toolsets, issues)
        _require_in("disabled_toolset", "learnbuddy_learning", disabled_toolsets, issues)
        model = _mapping(config.get("model"))
        if not model.get("provider") or not model.get("default"):
            issues.append("missing_model")
        required_env = {"LEARNBUDDY_CONFIG_PATH", "TELEGRAM_BOT_TOKEN", "TELEGRAM_HOME_CHANNEL"}
        if "TELEGRAM_ALLOWED_USERS" not in _env_keys(env_path) and "TELEGRAM_ALLOWED_CHATS" not in _env_keys(env_path):
            issues.append("missing_env_key:TELEGRAM_ALLOWED_USERS_or_TELEGRAM_ALLOWED_CHATS")
        if "TELEGRAM_FREE_RESPONSE_CHATS" not in _env_keys(env_path):
            issues.append("missing_env_key:TELEGRAM_FREE_RESPONSE_CHATS")
    env_keys = _env_keys(env_path)
    for key in sorted(required_env):
        if key not in env_keys:
            issues.append(f"missing_env_key:{key}")
    return {
        "name": f"{role}_profile",
        "status": "error" if issues else "ok",
        "profile": profile,
        "path": str(profile_dir),
        "plugin_installed": plugin_yaml.exists(),
        "telegram_toolsets": telegram_toolsets,
        "known_plugin_toolsets": known_toolsets,
        "disabled_toolsets_checked": sorted(set(disabled_toolsets).intersection(FORBIDDEN_CHILD_TOOLSETS | {"learnbuddy_child", "learnbuddy_learning"})),
        "env_keys_present": sorted(key for key in env_keys if key.startswith("LEARNBUDDY_") or key.startswith("TELEGRAM_")),
        "issues": issues,
    }


def _child_gateway_service_check(unit_dir: Path, service: str, *, expected_profile: str) -> dict[str, Any]:
    unit_name = service if service.endswith(".service") else f"{service}.service"
    unit_path = unit_dir / unit_name
    text = unit_path.read_text(encoding="utf-8") if unit_path.exists() else ""
    issues: list[str] = []
    if not unit_path.exists():
        issues.append("missing_unit")
    if expected_profile and f"--profile {expected_profile}" not in text:
        issues.append("missing_expected_profile")
    if "gateway run" not in text:
        issues.append("missing_gateway_run")
    return {
        "name": "child_gateway_service",
        "status": "error" if issues else "ok",
        "unit": unit_name,
        "path": str(unit_path),
        "expected_profile": expected_profile,
        "issues": issues,
    }


def _dispatch_timer_check(unit_dir: Path, profile: str) -> dict[str, Any]:
    service_name = f"learnbuddy-dispatch-{profile}.service"
    timer_name = f"learnbuddy-dispatch-{profile}.timer"
    service_path = unit_dir / service_name
    timer_path = unit_dir / timer_name
    service_text = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
    timer_text = timer_path.read_text(encoding="utf-8") if timer_path.exists() else ""
    issues: list[str] = []
    if not service_path.exists():
        issues.append("missing_service_unit")
    if not timer_path.exists():
        issues.append("missing_timer_unit")
    if "dispatch-plan" not in service_text:
        issues.append("missing_dispatch_plan_exec")
    if "--config" not in service_text:
        issues.append("missing_explicit_config")
    if "Persistent=true" not in timer_text:
        issues.append("missing_persistent_true")
    if "OnUnitActiveSec" not in timer_text:
        issues.append("missing_on_unit_active_sec")
    return {
        "name": "dispatch_timer",
        "status": "error" if issues else "ok",
        "profile": profile,
        "service": service_name,
        "timer": timer_name,
        "service_path": str(service_path),
        "timer_path": str(timer_path),
        "issues": issues,
    }


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _env_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _value = line.split("=", 1)
        keys.add(key.strip())
    return keys


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _require_in(label: str, value: str, values: list[str], issues: list[str]) -> None:
    if value not in values:
        issues.append(f"missing_{label}:{value}")


def _forbid_in(label: str, value: str, values: list[str], issues: list[str]) -> None:
    if value in values:
        issues.append(f"forbidden_{label}:{value}")


def _format_check(check: dict[str, Any]) -> str:
    fields: list[str] = [f"check={check['name']}", f"status={check['status']}"]
    for key in [
        "missing",
        "mode",
        "path",
        "exists",
        "parent_exists",
        "parent_writable",
        "creatable",
        "unwritable_files",
        "profile",
        "unit",
        "service",
        "timer",
        "issues",
        "error",
    ]:
        if key not in check:
            continue
        value = check[key]
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        fields.append(f"{key}={value}")
    return " ".join(fields)
