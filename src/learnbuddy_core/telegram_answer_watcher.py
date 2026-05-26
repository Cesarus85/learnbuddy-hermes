"""One-shot Telegram child-answer watcher for LearnBuddy.

This module deliberately handles only the narrow LearnBuddy answer loop:
child reply in the configured child Telegram chat -> evaluate current pending
exercise -> send child feedback -> notify parent. It is not a generic child
chatbot gateway.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import urllib.error
import urllib.request

from .config import LearnBuddyConfig
from .delivery import DeliveryMessage, delivery_adapter_from_config
from .runtime import LearnBuddyRuntime

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


def load_env_file(path: str | Path | None) -> None:
    """Load KEY=VALUE pairs without printing or returning secret values."""
    if not path:
        return
    env_path = Path(path).expanduser()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def process_child_telegram_answers(
    config: LearnBuddyConfig,
    *,
    env_file: str | Path | None = None,
    state_file: str | Path | None = None,
    send_feedback: bool = True,
    notify_parent: bool = True,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Process at most one child Telegram answer for the current pending task."""
    load_env_file(env_file)
    runtime = LearnBuddyRuntime(
        config.resolved_storage_dir(),
        max_attempts=config.max_attempts,
        child_id=config.child_id,
        child_name=config.child_name,
        agent_name=config.agent_name,
    )
    storage_dir = config.resolved_storage_dir()
    watch_state_path = Path(state_file).expanduser() if state_file else storage_dir / "telegram_answer_watch_state.json"
    watch_state = _read_json(watch_state_path, {})
    token = os.getenv(config.child_telegram_bot_token_env)
    chat_id = os.getenv(config.child_telegram_chat_id_env)
    missing = [
        name
        for name, value in (
            (config.child_telegram_bot_token_env, token),
            (config.child_telegram_chat_id_env, chat_id),
        )
        if not value
    ]
    if missing:
        return {"status": "not_configured", "missing": missing}

    pending = runtime.status().get("pending")
    if not pending:
        return {"status": "no_pending"}

    assert token is not None
    assert chat_id is not None
    api_transport = transport or _telegram_transport
    offset = watch_state.get("offset")
    payload: dict[str, Any] = {"limit": 50, "timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = int(offset)
    try:
        updates_response = _telegram_api(token, "getUpdates", payload, api_transport)
    except Exception:
        return {"status": "error", "error": "telegram getUpdates failed"}
    if updates_response.get("ok") is not True:
        return {"status": "error", "error": "telegram getUpdates failed"}

    updates = updates_response.get("result") or []
    if not isinstance(updates, list):
        return {"status": "error", "error": "telegram getUpdates returned invalid result"}

    pending_since = _parse_iso(str(pending.get("timestamp") or ""))
    candidate = _find_answer_update(updates, allowed_chat_id=str(chat_id), pending_since=pending_since)
    if not candidate:
        _advance_offset(watch_state_path, watch_state, updates)
        return {"status": "no_answer", "updates_seen": len(updates)}

    message = candidate["message"]
    answer_text = str(message.get("text") or "").strip()
    result = runtime.submit_answer(answer_text, input_mode="text")
    child_delivery = None
    parent_delivery = None
    if send_feedback:
        child_delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
            DeliveryMessage(text=str(result.get("feedback") or ""), metadata={"kind": "answer_feedback", "session_id": pending.get("id")})
        ).to_dict()
    if notify_parent:
        parent_text = _render_parent_answer_notification(config, pending, answer_text, result)
        parent_delivery = delivery_adapter_from_config(config, recipient="parent").deliver_parent(
            DeliveryMessage(text=parent_text, metadata={"kind": "answer_result", "session_id": pending.get("id")})
        ).to_dict()

    _advance_offset(watch_state_path, watch_state, updates, minimum_next=int(candidate["update_id"]) + 1)
    return {
        "status": "processed",
        "update_id": candidate["update_id"],
        "message_id": message.get("message_id"),
        "result": result.get("result"),
        "correct": result.get("correct"),
        "attempts": result.get("attempts"),
        "max_attempts": result.get("max_attempts"),
        "child_delivery": child_delivery,
        "parent_delivery": parent_delivery,
    }


def _telegram_api(token: str, method: str, payload: dict[str, Any], transport: Transport) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    return transport(url, payload)


def _telegram_transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - Telegram API endpoint from user token
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Telegram response root must be a mapping")
    return parsed


def _find_answer_update(updates: list[Any], *, allowed_chat_id: str, pending_since: datetime | None) -> dict[str, Any] | None:
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get("message")
        if not isinstance(message, dict):
            continue
        raw_chat = message.get("chat")
        chat = raw_chat if isinstance(raw_chat, dict) else {}
        raw_sender = message.get("from")
        sender = raw_sender if isinstance(raw_sender, dict) else {}
        text = str(message.get("text") or "").strip()
        if str(chat.get("id")) != allowed_chat_id:
            continue
        if sender.get("is_bot") is True:
            continue
        if not text or text.startswith("/"):
            continue
        if pending_since is not None:
            message_date = message.get("date")
            if isinstance(message_date, (int, float)) and datetime.fromtimestamp(message_date, timezone.utc) < pending_since:
                continue
        return {"update_id": update.get("update_id"), "message": message}
    return None


def _render_parent_answer_notification(config: LearnBuddyConfig, pending: dict[str, Any], answer_text: str, result: dict[str, Any]) -> str:
    verdict = "richtig" if result.get("correct") is True else "noch nicht richtig"
    if result.get("result") == "exhausted":
        verdict = "nicht richtig — alle Versuche aufgebraucht"
    attempts = result.get("attempts")
    max_attempts = result.get("max_attempts")
    return (
        f"📚 {config.agent_name}: {config.child_name} hat geantwortet\n"
        f"Aufgabe: {pending.get('prompt')}\n"
        f"Antwort: {answer_text}\n"
        f"Ergebnis: {verdict}, Versuch {attempts}/{max_attempts}."
    )


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _advance_offset(path: Path, state: dict[str, Any], updates: list[Any], *, minimum_next: int | None = None) -> None:
    next_offset = minimum_next
    for update in updates:
        if isinstance(update, dict) and isinstance(update.get("update_id"), int):
            candidate = int(update["update_id"]) + 1
            next_offset = candidate if next_offset is None else max(next_offset, candidate)
    if next_offset is None:
        return
    state = dict(state)
    state["offset"] = next_offset
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
