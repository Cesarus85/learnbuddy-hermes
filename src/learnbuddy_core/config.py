"""Configuration loading for LearnBuddy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import yaml


@dataclass(frozen=True)
class LearnBuddyConfig:
    child_id: str = "learner"
    child_name: str = "Learner"
    agent_name: str = "LearnBuddy"
    family_language: str = "de"
    timezone: str = "Europe/Berlin"
    storage_dir: str | None = None
    max_attempts: int = 3
    delivery_mode: str = "dry_run"
    child_telegram_bot_token_env: str = "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN"
    child_telegram_chat_id_env: str = "LEARNBUDDY_ALLOWED_CHILD_CHAT_ID"
    parent_telegram_bot_token_env: str = "LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN"
    parent_telegram_chat_id_env: str = "LEARNBUDDY_ALLOWED_PARENT_CHAT_ID"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LearnBuddyConfig":
        config_path = Path(path).expanduser()
        return cls.from_mapping(load_yaml_config(config_path), base_dir=config_path.parent)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, base_dir: Path | None = None) -> "LearnBuddyConfig":
        child = _mapping(data.get("child"))
        children = data.get("children")
        if not child and isinstance(children, list) and children:
            child = _mapping(children[0])
        family = _mapping(data.get("family"))
        agent = data.get("agent")
        agent_map = _mapping(agent)
        safety = _mapping(data.get("safety"))
        storage = _mapping(data.get("storage"))
        delivery = _mapping(data.get("delivery"))
        telegram = _mapping(delivery.get("telegram"))
        child_delivery = _mapping(delivery.get("child"))
        child_delivery_type = child_delivery.get("type")
        parent_delivery = _mapping(delivery.get("parent"))
        parents = delivery.get("parents")
        if not parent_delivery and isinstance(parents, list) and parents:
            parent_delivery = _mapping(parents[0])

        storage_dir = data.get("storage_dir") or storage.get("data_dir")
        if storage_dir is not None:
            storage_dir = _resolve_path_string(str(storage_dir), base_dir=base_dir)

        return cls(
            child_id=str(child.get("id") or child.get("child_id") or data.get("child_id") or cls.child_id),
            child_name=str(child.get("display_name") or child.get("name") or data.get("child_name") or cls.child_name),
            agent_name=str(
                agent_map.get("name")
                or (agent if isinstance(agent, str) else None)
                or child.get("agent_name")
                or data.get("agent_name")
                or cls.agent_name
            ),
            family_language=str(family.get("language") or data.get("family_language") or data.get("language") or cls.family_language),
            timezone=str(family.get("timezone") or safety.get("timezone") or data.get("timezone") or cls.timezone),
            storage_dir=storage_dir,
            max_attempts=int(safety.get("max_attempts") or child.get("max_attempts") or data.get("max_attempts") or cls.max_attempts),
            delivery_mode=str(delivery.get("mode") or child_delivery_type or cls.delivery_mode),
            child_telegram_bot_token_env=str(
                telegram.get("child_bot_env")
                or child_delivery.get("bot_token_env")
                or cls.child_telegram_bot_token_env
            ),
            child_telegram_chat_id_env=str(
                telegram.get("allowed_child_chat_id_env")
                or child_delivery.get("allowed_chat_ids_env")
                or child_delivery.get("chat_id_env")
                or cls.child_telegram_chat_id_env
            ),
            parent_telegram_bot_token_env=str(
                telegram.get("parent_bot_env")
                or parent_delivery.get("bot_token_env")
                or cls.parent_telegram_bot_token_env
            ),
            parent_telegram_chat_id_env=str(
                telegram.get("parent_chat_id_env")
                or parent_delivery.get("target_env")
                or parent_delivery.get("chat_id_env")
                or parent_delivery.get("allowed_chat_ids_env")
                or cls.parent_telegram_chat_id_env
            ),
        )

    def resolved_storage_dir(self) -> Path:
        if self.storage_dir:
            return Path(os.path.expandvars(self.storage_dir)).expanduser()
        return default_storage_dir()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_path_string(value: str, *, base_dir: Path | None) -> str:
    expanded = _expand_known_defaults(value)
    path = Path(expanded).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return str(path)


def _expand_known_defaults(value: str) -> str:
    if "HERMES_HOME" in value and "HERMES_HOME" not in os.environ:
        default_hermes_home = str(Path("~/.hermes").expanduser())
        value = value.replace("${HERMES_HOME}", default_hermes_home).replace("$HERMES_HOME", default_hermes_home)
    return os.path.expandvars(value)


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a mapping")
    return data


def default_storage_dir() -> Path:
    explicit = os.getenv("LEARNBUDDY_STORAGE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    hermes_home = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
    return hermes_home / "family" / "learnbuddy"
