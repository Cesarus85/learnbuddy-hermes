"""One-shot Telegram child-answer watcher for LearnBuddy.

This module deliberately handles only the narrow LearnBuddy answer loop:
child reply in the configured child Telegram chat -> evaluate current pending
exercise -> send child feedback -> notify parent. It is not a generic child
chatbot gateway.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo
import json
import os
import urllib.error
import urllib.request

from .child_intent import IntentClassifierConfig, classify_child_intent
from .config import LearnBuddyConfig
from .delivery import DeliveryMessage, delivery_adapter_from_config
from .notifier import ParentNotifier
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
    intent_config: IntentClassifierConfig | None = None,
    now: str | datetime | None = None,
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

    pending_since = _parse_iso(str(pending.get("timestamp") or "")) if isinstance(pending, dict) else None
    candidate = _find_answer_update(updates, allowed_chat_id=str(chat_id), pending_since=pending_since)
    if not candidate:
        _advance_offset(watch_state_path, watch_state, updates)
        if isinstance(pending, dict):
            pending_delivery = _deliver_pending_child_prompt_if_needed(config, runtime, pending)
            return {"status": "no_answer", "updates_seen": len(updates), "pending_delivery": pending_delivery}
        return {"status": "no_pending", "updates_seen": len(updates)}

    message = candidate["message"]
    answer_text = str(message.get("text") or "").strip()
    child_command = classify_child_intent(answer_text, intent_config)
    if child_command:
        if isinstance(pending, dict):
            command_result = _handle_child_control_message(
                config,
                runtime,
                pending,
                answer_text=answer_text,
                command=child_command,
                send_feedback=send_feedback,
                notify_parent=notify_parent,
                now=now,
            )
        else:
            command_result = _handle_child_control_message_without_pending(
                config,
                runtime,
                answer_text=answer_text,
                command=child_command,
                send_feedback=send_feedback,
                notify_parent=notify_parent,
                now=now,
            )
        _advance_offset(watch_state_path, watch_state, updates, minimum_next=int(candidate["update_id"]) + 1)
        return {
            "status": "child_command",
            "update_id": candidate["update_id"],
            "message_id": message.get("message_id"),
            **command_result,
        }
    if not isinstance(pending, dict):
        _advance_offset(watch_state_path, watch_state, updates, minimum_next=int(candidate["update_id"]) + 1)
        return {"status": "no_pending", "update_id": candidate["update_id"], "message_id": message.get("message_id")}
    result = runtime.submit_answer(answer_text, input_mode="text")
    promoted_session = result.get("promoted_session") if isinstance(result.get("promoted_session"), dict) else None
    child_delivery = None
    next_child_delivery = None
    parent_delivery = None
    if send_feedback:
        child_adapter = delivery_adapter_from_config(config, recipient="child")
        child_delivery = child_adapter.deliver_child(
            DeliveryMessage(text=str(result.get("feedback") or ""), metadata={"kind": "answer_feedback", "session_id": pending.get("id")})
        ).to_dict()
        if promoted_session:
            next_child_delivery = child_adapter.deliver_child(
                DeliveryMessage(
                    text=str(promoted_session.get("prompt") or ""),
                    metadata={"kind": "promoted_exercise", "session_id": promoted_session.get("id")},
                )
            ).to_dict()
            runtime.mark_pending_delivery(next_child_delivery)
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
        "next_child_delivery": next_child_delivery,
        "parent_delivery": parent_delivery,
        "promoted_session": promoted_session,
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


def _delivery_succeeded(status: Any) -> bool:
    return str(status or "") in {"sent", "dry_run"}


def _deliver_pending_child_prompt_if_needed(config: LearnBuddyConfig, runtime: LearnBuddyRuntime, pending: dict[str, Any]) -> dict[str, Any] | None:
    raw_delivery = pending.get("delivery")
    delivery = raw_delivery if isinstance(raw_delivery, dict) else {}
    raw_child_delivery = delivery.get("child")
    child_delivery = raw_child_delivery if isinstance(raw_child_delivery, dict) else {}
    if _delivery_succeeded(child_delivery.get("status")):
        return child_delivery
    child_adapter = delivery_adapter_from_config(config, recipient="child")
    result = child_adapter.deliver_child(
        DeliveryMessage(
            text=str(pending.get("prompt") or ""),
            metadata={"kind": "pending_exercise_repair", "session_id": pending.get("id")},
        )
    ).to_dict()
    runtime.mark_pending_delivery(result)
    return result


def _with_metadata(delivery: dict[str, Any] | None, metadata: dict[str, Any], *, text: str | None = None) -> dict[str, Any] | None:
    if delivery is None:
        return None
    result = dict(delivery)
    result["metadata"] = metadata
    if text is not None:
        result["text"] = text
    return result


def _handle_child_control_message(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    pending: dict[str, Any],
    *,
    answer_text: str,
    command: str,
    send_feedback: bool,
    notify_parent: bool,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    if command == "repeat":
        metadata = {"kind": "pending_exercise_repeat", "session_id": pending.get("id")}
        child_delivery = None
        if send_feedback:
            child_delivery = _with_metadata(
                delivery_adapter_from_config(config, recipient="child").deliver_child(
                    DeliveryMessage(text=f"Hier ist die Aufgabe nochmal:\n{pending.get('prompt')}", metadata=metadata)
                ).to_dict(),
                metadata,
            )
            if child_delivery is not None:
                runtime.mark_pending_delivery(child_delivery)
        return {"command": "repeat", "child_delivery": child_delivery, "parent_delivery": None}

    if command == "help":
        reason = f"{config.child_name} bittet per Telegram um Hilfe: {answer_text}. Offene Aufgabe: {pending.get('prompt')}"
        help_request = runtime.create_parent_help_request(
            reason,
            subject=str(pending.get("subject") or "general"),
            requested_by="child",
        )
        child_metadata = {"kind": "child_help_ack", "session_id": pending.get("id"), "help_request_id": help_request.get("id")}
        child_delivery = None
        if send_feedback:
            child_delivery = _with_metadata(
                delivery_adapter_from_config(config, recipient="child").deliver_child(
                    DeliveryMessage(
                        text="Ich habe deinen Eltern Bescheid gesagt. Die Aufgabe bleibt offen — du kannst später weiter antworten.",
                        metadata=child_metadata,
                    )
                ).to_dict(),
                child_metadata,
            )
        parent_delivery = None
        if notify_parent:
            parent_delivery = _with_metadata(
                ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_help_request(help_request).to_dict(),
                {"kind": "parent_help_request", "help_request_id": help_request.get("id"), "session_id": pending.get("id")},
            )
        return {"command": "help", "help_request": help_request, "child_delivery": child_delivery, "parent_delivery": parent_delivery}

    if command == "next":
        metadata = {"kind": "finish_pending_first", "session_id": pending.get("id")}
        text = f"Erst diese Aufgabe lösen, dann gibt’s die nächste:\n{pending.get('prompt')}"
        child_delivery = None
        if send_feedback:
            child_delivery = _with_metadata(
                delivery_adapter_from_config(config, recipient="child").deliver_child(
                    DeliveryMessage(text=text, metadata=metadata)
                ).to_dict(),
                metadata,
                text=text,
            )
        return {"command": "next", "dispatch": {"status": "pending_exists", "pending": pending}, "child_delivery": child_delivery, "parent_delivery": None}

    return {"command": command, "child_delivery": None, "parent_delivery": None}


def _handle_child_control_message_without_pending(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    *,
    answer_text: str,
    command: str,
    send_feedback: bool,
    notify_parent: bool,
    now: str | datetime | None,
) -> dict[str, Any]:
    if command == "next":
        dispatch, child_delivery, help_request, parent_delivery = _dispatch_child_requested_next_exercise(
            config,
            runtime,
            answer_text=answer_text,
            send_feedback=send_feedback,
            notify_parent=notify_parent,
            now=now,
        )
        result: dict[str, Any] = {"command": "next", "dispatch": dispatch, "child_delivery": child_delivery, "parent_delivery": parent_delivery}
        if help_request is not None:
            result["help_request"] = help_request
        return result

    metadata = {"kind": "no_pending_child_command", "command": command}
    text = "Gerade ist keine Aufgabe offen. Wenn du weiter üben möchtest, schreib: Noch eine."
    child_delivery = None
    if send_feedback:
        child_delivery = _with_metadata(
            delivery_adapter_from_config(config, recipient="child").deliver_child(DeliveryMessage(text=text, metadata=metadata)).to_dict(),
            metadata,
            text=text,
        )
    return {"command": command, "dispatch": {"status": "no_pending"}, "child_delivery": child_delivery, "parent_delivery": None}


def _dispatch_child_requested_next_exercise(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    *,
    answer_text: str,
    send_feedback: bool,
    notify_parent: bool,
    now: str | datetime | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    current_time = _parse_policy_datetime(now, config.timezone)
    if not _inside_allowed_hours(current_time, config.allowed_hours_from, config.allowed_hours_to):
        dispatch = {
            "status": "outside_allowed_hours",
            "now": current_time.isoformat(),
            "allowed_hours": {"from": config.allowed_hours_from, "to": config.allowed_hours_to},
        }
        child_delivery = _deliver_child_next_rejection(config, dispatch, "Jetzt ist gerade Lernpause. Frag deine Eltern, wenn du trotzdem üben möchtest.", send_feedback)
        help_request, parent_delivery = _notify_parent_about_child_next_block(config, runtime, answer_text, dispatch, notify_parent=notify_parent)
        return dispatch, child_delivery, help_request, parent_delivery

    state = runtime.status()
    if isinstance(state.get("pending"), dict):
        dispatch = {"status": "pending_exists", "pending": state.get("pending")}
        child_delivery = _deliver_child_next_rejection(config, dispatch, "Erst diese Aufgabe lösen, dann gibt’s die nächste.", send_feedback)
        return dispatch, child_delivery, None, None

    auto_count = _auto_sessions_today(runtime, current_time, config.timezone)
    if auto_count >= config.daily_auto_limit:
        dispatch = {"status": "daily_limit_reached", "daily_auto_limit": config.daily_auto_limit, "auto_sessions_today": auto_count}
        child_delivery = _deliver_child_next_rejection(config, dispatch, "Für heute reicht’s erstmal. Frag deine Eltern, wenn du noch mehr üben möchtest.", send_feedback)
        help_request, parent_delivery = _notify_parent_about_child_next_block(config, runtime, answer_text, dispatch, notify_parent=notify_parent)
        return dispatch, child_delivery, help_request, parent_delivery

    try:
        result = runtime.open_exercise(
            mode="auto",
            requested_by="system",
            timestamp=current_time.astimezone(timezone.utc).isoformat(),
        )
    except KeyError as exc:
        dispatch = {"status": "no_matching_exercise", "error": str(exc)}
        child_delivery = _deliver_child_next_rejection(config, dispatch, "Ich habe gerade keine passende Aufgabe. Ich habe deinen Eltern Bescheid gesagt.", send_feedback)
        help_request, parent_delivery = _notify_parent_about_child_next_block(config, runtime, answer_text, dispatch, notify_parent=notify_parent)
        return dispatch, child_delivery, help_request, parent_delivery

    if result.get("status") != "opened":
        dispatch = dict(result)
        child_delivery = _deliver_child_next_rejection(config, dispatch, "Ich kann gerade keine neue Aufgabe öffnen. Ich habe deinen Eltern kurz Bescheid gesagt.", send_feedback)
        help_request, parent_delivery = _notify_parent_about_child_next_block(config, runtime, answer_text, dispatch, notify_parent=notify_parent)
        return dispatch, child_delivery, help_request, parent_delivery

    session = result.get("session") if isinstance(result.get("session"), dict) else {}
    metadata = {"kind": "child_requested_next_exercise", "session_id": session.get("id")}
    text = str(session.get("prompt") or result.get("prompt") or "")
    child_delivery = None
    dispatch = dict(result)
    if send_feedback:
        child_delivery = _with_metadata(
            delivery_adapter_from_config(config, recipient="child").deliver_child(DeliveryMessage(text=text, metadata=metadata)).to_dict(),
            metadata,
            text=text,
        )
        if child_delivery is not None:
            updated_session = runtime.mark_pending_delivery(child_delivery)
            dispatch["delivery"] = child_delivery
            dispatch["delivery_status"] = child_delivery.get("status")
            dispatch["session"] = updated_session or session
    return dispatch, child_delivery, None, None


def _notify_parent_about_child_next_block(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    answer_text: str,
    dispatch: dict[str, Any],
    *,
    notify_parent: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Create and optionally deliver a parent-facing note when a child asks for more but policy/storage blocks it."""
    reason = (
        f"{config.child_name} bittet per Telegram um eine weitere Aufgabe: {answer_text}. "
        f"LearnBuddy konnte keine neue Aufgabe öffnen (Grund: {dispatch.get('status')})."
    )
    help_request = runtime.create_parent_help_request(reason, subject="general", requested_by="child")
    parent_delivery = None
    if notify_parent:
        parent_delivery = _with_metadata(
            ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_help_request(help_request).to_dict(),
            {"kind": "parent_help_request", "help_request_id": help_request.get("id"), "reason": dispatch.get("status")},
        )
    return help_request, parent_delivery


def _deliver_child_next_rejection(
    config: LearnBuddyConfig,
    dispatch: dict[str, Any],
    text: str,
    send_feedback: bool,
) -> dict[str, Any] | None:
    if not send_feedback:
        return None
    metadata = {"kind": "child_next_rejected", "reason": dispatch.get("status")}
    return _with_metadata(
        delivery_adapter_from_config(config, recipient="child").deliver_child(DeliveryMessage(text=text, metadata=metadata)).to_dict(),
        metadata,
        text=text,
    )


def _parse_policy_datetime(value: str | datetime | None, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    if isinstance(value, datetime):
        parsed = value
    elif value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        return datetime.now(zone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _parse_clock(value: str) -> time:
    return time.fromisoformat(value)


def _inside_allowed_hours(now: datetime, start_text: str, end_text: str) -> bool:
    current = now.time().replace(second=0, microsecond=0)
    start = _parse_clock(start_text)
    end = _parse_clock(end_text)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _auto_sessions_today(runtime: LearnBuddyRuntime, now: datetime, timezone_name: str) -> int:
    zone = ZoneInfo(timezone_name)
    count = 0
    for session in runtime.sessions():
        if session.get("mode") != "auto":
            continue
        timestamp = session.get("timestamp")
        if not timestamp:
            continue
        session_time = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if session_time.tzinfo is None:
            session_time = session_time.replace(tzinfo=timezone.utc)
        if session_time.astimezone(zone).date() == now.date():
            count += 1
    return count


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
