"""Public-safe setup and backup helpers for LearnBuddy."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import zipfile

import yaml

from .config import default_storage_dir
from .runtime import RuntimePaths

_RUNTIME_FILE_NAMES = (
    "state.json",
    "exercises.jsonl",
    "sessions.jsonl",
    "answers.jsonl",
    "help_requests.jsonl",
    "scheduled_exercises.jsonl",
)
_MANIFEST_NAME = "learnbuddy-backup-manifest.json"


def create_setup(
    *,
    config_path: str | Path,
    data_dir: str | Path | None = None,
    child_id: str = "learner",
    child_name: str = "Learner",
    agent_name: str = "LearnBuddy",
    delivery_mode: str = "dry_run",
    force: bool = False,
) -> dict[str, Any]:
    """Create a minimal local config and storage directory.

    The generated file deliberately contains no secrets and, in dry-run mode, no
    token/chat env-var names. Telegram env names can be documented separately and
    added by the operator after setup.
    """
    config = Path(config_path).expanduser()
    storage = Path(data_dir).expanduser() if data_dir is not None else default_storage_dir()
    if config.exists() and not force:
        return {"status": "exists", "config_path": str(config), "error": "config already exists; use --force to overwrite"}

    config.parent.mkdir(parents=True, exist_ok=True)
    storage.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "child": {"id": child_id, "display_name": child_name},
        "agent": {"name": agent_name},
        "safety": {"max_attempts": 3, "daily_auto_limit": 1, "allowed_hours": {"from": "07:00", "to": "21:00"}},
        "storage": {"data_dir": str(storage)},
        "delivery": {"mode": delivery_mode},
    }
    config.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"status": "created", "config_path": str(config), "storage_dir": str(storage)}


def backup_runtime_data(*, data_dir: str | Path, output: str | Path) -> dict[str, Any]:
    """Create a zip archive containing only the public runtime data files."""
    source = Path(data_dir).expanduser()
    archive = Path(output).expanduser()
    paths = RuntimePaths(source)
    files: list[str] = []
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in _RUNTIME_FILE_NAMES:
            path = getattr(paths, name.split(".")[0] if name != "state.json" else "state")
            if path.exists():
                zf.write(path, arcname=name)
                files.append(name)
        manifest = {"format": "learnbuddy-runtime-backup-v1", "files": files}
        zf.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "created", "archive_path": str(archive), "data_dir": str(source), "files": files}


def restore_runtime_data(*, archive: str | Path, data_dir: str | Path, force: bool = False) -> dict[str, Any]:
    """Restore a LearnBuddy runtime backup into a storage directory."""
    archive_path = Path(archive).expanduser()
    target = Path(data_dir).expanduser()
    if not archive_path.exists():
        return {"status": "missing", "archive_path": str(archive_path), "error": "backup archive does not exist"}

    with zipfile.ZipFile(archive_path) as zf:
        names = [name for name in zf.namelist() if name != _MANIFEST_NAME]
        unsafe = [name for name in names if name not in _RUNTIME_FILE_NAMES or Path(name).is_absolute() or ".." in Path(name).parts]
        if unsafe:
            return {"status": "invalid", "archive_path": str(archive_path), "error": "backup archive contains unsupported paths"}
        existing = [name for name in names if (target / name).exists()]
        if existing and not force:
            return {
                "status": "exists",
                "archive_path": str(archive_path),
                "data_dir": str(target),
                "files": existing,
                "error": "target data exists; use --force to overwrite",
            }
        target.mkdir(parents=True, exist_ok=True)
        for name in names:
            (target / name).write_bytes(zf.read(name))
    return {"status": "restored", "archive_path": str(archive_path), "data_dir": str(target), "files": names}
