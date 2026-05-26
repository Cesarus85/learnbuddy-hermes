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


def render_parent_help_request_notification(request: dict[str, Any]) -> str:
    if request.get("text"):
        return str(request["text"])
    child_name = str(request.get("child_name") or "Learner")
    agent_name = str(request.get("agent_name") or "LearnBuddy")
    reason = str(request.get("reason") or "needs help")
    subject = request.get("subject")
    prefix = "Dringende Elternhilfe" if request.get("urgent") else "Elternhilfe"
    subject_text = f" in {subject}" if subject else ""
    return f"{agent_name}: {prefix} für {child_name}{subject_text}: {reason}"


class ParentNotifier:
    """Send parent-facing notifications through a configured delivery adapter."""

    def __init__(self, delivery_adapter: Any) -> None:
        self.delivery_adapter = delivery_adapter

    def notify_report(self, report: dict[str, Any]) -> DeliveryResult:
        return self.delivery_adapter.deliver_parent(DeliveryMessage(text=render_parent_report_notification(report), metadata={"kind": "parent_report"}))

    def notify_help_request(self, request: dict[str, Any]) -> DeliveryResult:
        return self.delivery_adapter.deliver_parent(DeliveryMessage(text=render_parent_help_request_notification(request), metadata={"kind": "parent_help_request"}))
