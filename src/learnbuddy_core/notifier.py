"""Parent-facing notification rendering and dispatch."""
from __future__ import annotations

from typing import Any

from .delivery import DeliveryMessage, DeliveryResult


def render_parent_report_notification(report: dict[str, Any]) -> str:
    if report.get("text"):
        return str(report["text"])
    child_name = str(report.get("child_name") or "Learner")
    agent_name = str(report.get("agent_name") or "LearnBuddy")
    correct = int(report.get("correct") or 0)
    answers = int(report.get("answers") or 0)
    exhausted = int(report.get("exhausted") or 0)
    return f"{agent_name} Status für {child_name}: {correct}/{answers} richtig, {exhausted} Aufgaben mit aufgebrauchten Versuchen."


class ParentNotifier:
    """Send parent-facing notifications through a configured delivery adapter."""

    def __init__(self, delivery_adapter: Any) -> None:
        self.delivery_adapter = delivery_adapter

    def notify_report(self, report: dict[str, Any]) -> DeliveryResult:
        return self.delivery_adapter.deliver_parent(DeliveryMessage(text=render_parent_report_notification(report), metadata={"kind": "parent_report"}))
