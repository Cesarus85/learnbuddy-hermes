from learnbuddy_core.delivery import DryRunDeliveryAdapter
from learnbuddy_core.notifier import ParentNotifier, render_parent_report_notification


def test_render_parent_report_notification_uses_report_text():
    report = {
        "child_name": "Emma",
        "agent_name": "Lumi",
        "answers": 4,
        "correct": 3,
        "exhausted": 1,
        "text": "Lumi Status für Emma: 3/4 richtig, 1 Aufgaben mit aufgebrauchten Versuchen.",
    }

    text = render_parent_report_notification(report)

    assert text == "Lumi Status für Emma: 3/4 richtig, 1 Aufgaben mit aufgebrauchten Versuchen."


def test_render_parent_report_notification_has_safe_fallback():
    text = render_parent_report_notification({"child_name": "Emma", "agent_name": "Lumi", "answers": 2, "correct": 1, "exhausted": 0})

    assert text == "Lumi Status für Emma: 1/2 richtig, 0 Aufgaben mit aufgebrauchten Versuchen."


def test_parent_notifier_uses_delivery_adapter_parent_target():
    notifier = ParentNotifier(DryRunDeliveryAdapter())

    result = notifier.notify_report({"child_name": "Emma", "agent_name": "Lumi", "answers": 1, "correct": 1, "exhausted": 0})

    assert result.to_dict() == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "parent",
        "message_id": None,
        "error": None,
    }
