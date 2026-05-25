"""Configuration loading for LearnBuddy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import yaml


@dataclass(frozen=True)
class LearnBuddyConfig:
    family_language: str = "de"
    timezone: str = "Europe/Berlin"
    storage_dir: str = "~/.hermes/family/learnbuddy"


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
