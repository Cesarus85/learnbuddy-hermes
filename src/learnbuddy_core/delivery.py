"""Delivery adapters for public LearnBuddy transports.

Adapters keep transport-specific details out of the learning runtime. They return
small public results and deliberately do not expose tokens or raw chat IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import json
import os
import urllib.error
import urllib.request


Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class DeliveryMessage:
    text: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    adapter: str
    target: str
    message_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "adapter": self.adapter,
            "target": self.target,
            "message_id": self.message_id,
            "error": self.error,
        }


class DryRunDeliveryAdapter:
    """Adapter used for tests, demos, and setup validation without network I/O."""

    def __init__(self, *, adapter_name: str = "dry_run") -> None:
        self.adapter_name = adapter_name

    def deliver_child(self, message: DeliveryMessage) -> DeliveryResult:
        return DeliveryResult(status="dry_run", adapter=self.adapter_name, target="child")

    def deliver_parent(self, message: DeliveryMessage) -> DeliveryResult:
        return DeliveryResult(status="dry_run", adapter=self.adapter_name, target="parent")


class TelegramDeliveryAdapter:
    """Telegram Bot API adapter with env-based secrets and injectable transport."""

    def __init__(self, *, bot_token_env: str, chat_id_env: str, transport: Transport | None = None) -> None:
        self.bot_token_env = bot_token_env
        self.chat_id_env = chat_id_env
        self.transport = transport or _telegram_transport

    def deliver_child(self, message: DeliveryMessage) -> DeliveryResult:
        return self._deliver(message)

    def deliver_parent(self, message: DeliveryMessage) -> DeliveryResult:
        return self._deliver(message)

    def _deliver(self, message: DeliveryMessage) -> DeliveryResult:
        token = os.getenv(self.bot_token_env)
        chat_id = os.getenv(self.chat_id_env)
        missing = [name for name, value in ((self.bot_token_env, token), (self.chat_id_env, chat_id)) if not value]
        if missing:
            return DeliveryResult(
                status="not_configured",
                adapter="telegram",
                target=self.chat_id_env,
                error=f"missing environment variables: {', '.join(missing)}",
            )

        assert token is not None
        assert chat_id is not None
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message.text}
        try:
            response = self.transport(url, payload)
        except (OSError, urllib.error.URLError):
            return DeliveryResult(status="error", adapter="telegram", target=self.chat_id_env, error="telegram delivery failed")
        except Exception:
            return DeliveryResult(status="error", adapter="telegram", target=self.chat_id_env, error="telegram delivery failed")

        if response.get("ok") is not True:
            return DeliveryResult(
                status="error",
                adapter="telegram",
                target=self.chat_id_env,
                error=str(response.get("description") or "telegram delivery failed"),
            )
        message_id = response.get("result", {}).get("message_id")
        return DeliveryResult(status="sent", adapter="telegram", target=self.chat_id_env, message_id=str(message_id) if message_id is not None else None)


def delivery_adapter_from_config(config: Any, *, recipient: str = "child"):
    mode = str(getattr(config, "delivery_mode", "dry_run"))
    if recipient not in {"child", "parent"}:
        raise ValueError(f"unsupported delivery recipient: {recipient}")
    if mode == "telegram":
        token_attr = f"{recipient}_telegram_bot_token_env"
        chat_attr = f"{recipient}_telegram_chat_id_env"
        return TelegramDeliveryAdapter(
            bot_token_env=str(getattr(config, token_attr)),
            chat_id_env=str(getattr(config, chat_attr)),
        )
    if mode == "dry_run":
        return DryRunDeliveryAdapter(adapter_name=mode)
    raise ValueError(f"unsupported delivery mode: {mode}")


def _telegram_transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - user-configured Telegram API endpoint
        data = response.read().decode("utf-8")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("Telegram response root must be a mapping")
    return parsed
