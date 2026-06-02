"""Pending exercise reminder runner for LearnBuddy.

This module turns runtime reminder plans into explicit child/parent delivery
side effects. It stays public-safe: no private names, tokens, or chat IDs are
hard-coded; delivery comes from the configured adapter.
"""
from __future__ import annotations

from typing import Any

from .delivery import DeliveryMessage, delivery_adapter_from_config
from .runtime import LearnBuddyRuntime


def _delivery_succeeded(status: Any) -> bool:
    return str(status or "") in {"sent", "dry_run"}


def run_pending_reminder(
    config: Any,
    runtime: LearnBuddyRuntime,
    *,
    mode: str = "child_parent",
    now: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send due reminders for the current pending exercise and persist success.

    The runtime decides *what* is due; this runner performs explicit delivery.
    ``dry_run=True`` plans the messages but deliberately avoids delivery and
    state writes.
    """
    plan = runtime.pending_reminder_plan(now=now, timezone_name=str(getattr(config, "timezone", "Europe/Berlin")), mode=mode)
    if plan.get("status") != "due":
        return {"status": plan.get("status"), "reason": plan.get("reason"), "plan": plan, "child_delivery": None, "parent_delivery": None}

    if dry_run:
        return {"status": "dry_run", "plan": plan, "child_delivery": None, "parent_delivery": None}

    child_delivery = None
    parent_delivery = None
    child = plan.get("child")
    parent = plan.get("parent")
    if isinstance(child, dict):
        child_delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
            DeliveryMessage(
                text=str(child.get("text") or ""),
                metadata={"kind": "pending_exercise_reminder", "session_id": plan.get("session_id"), "stage": child.get("stage")},
            )
        ).to_dict()
    if isinstance(parent, dict):
        parent_delivery = delivery_adapter_from_config(config, recipient="parent").deliver_parent(
            DeliveryMessage(
                text=str(parent.get("text") or ""),
                metadata={"kind": "pending_exercise_parent_escalation", "session_id": plan.get("session_id"), "stage": parent.get("stage")},
            )
        ).to_dict()

    runtime.mark_pending_reminder_sent(plan, child_delivery=child_delivery, parent_delivery=parent_delivery)
    deliveries = [delivery for delivery in (child_delivery, parent_delivery) if delivery is not None]
    if deliveries and all(_delivery_succeeded(delivery.get("status")) for delivery in deliveries):
        status = "sent"
    elif deliveries:
        status = str(next((delivery.get("status") for delivery in deliveries if not _delivery_succeeded(delivery.get("status"))), "error"))
    else:
        status = "not_due"
    return {"status": status, "plan": plan, "child_delivery": child_delivery, "parent_delivery": parent_delivery}
