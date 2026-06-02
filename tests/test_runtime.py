from pathlib import Path

from learnbuddy_core.config import LearnBuddyConfig, default_storage_dir
from learnbuddy_core.runtime import LearnBuddyRuntime


def test_default_storage_dir_uses_isolated_hermes_home(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("LEARNBUDDY_STORAGE_DIR", raising=False)

    assert default_storage_dir() == hermes_home / "family" / "learnbuddy"


def test_config_loads_child_and_agent_identity_from_yaml(tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
child:
  id: kid-1
  display_name: Alex
agent:
  name: BuddyBot
safety:
  max_attempts: 4
  queue_max: 2
  daily_auto_limit: 2
  allowed_hours:
    from: "08:30"
    to: "19:45"
storage:
  data_dir: ./learnbuddy-data
""".strip(),
        encoding="utf-8",
    )

    config = LearnBuddyConfig.from_yaml(config_path)

    assert config.child_id == "kid-1"
    assert config.child_name == "Alex"
    assert config.agent_name == "BuddyBot"
    assert config.max_attempts == 4
    assert config.queue_max == 2
    assert config.daily_auto_limit == 2
    assert config.allowed_hours_from == "08:30"
    assert config.allowed_hours_to == "19:45"
    assert config.storage_dir.endswith("learnbuddy-data")


def test_public_example_configs_expose_child_and_agent_identity():
    repo = Path(__file__).resolve().parents[1]
    telegram = LearnBuddyConfig.from_yaml(repo / "examples" / "single-child-telegram.yaml")
    vps = LearnBuddyConfig.from_yaml(repo / "examples" / "single-child-vps-cloud-llm.yaml")

    assert telegram.child_id == "emma"
    assert telegram.child_name == "Emma"
    assert telegram.agent_name == "Lumi"
    assert telegram.max_attempts == 3
    assert telegram.queue_max == 5
    assert telegram.daily_auto_limit == 1
    assert vps.child_id == "emma"
    assert vps.agent_name == "Lumi"
    assert vps.queue_max == 5


def test_config_supports_legacy_children_list_shape(tmp_path):
    config_path = tmp_path / "legacy.yaml"
    config_path.write_text(
        """
children:
  - id: emma
    name: Emma
    agent_name: Lumi
    max_attempts: 2
""".strip(),
        encoding="utf-8",
    )

    config = LearnBuddyConfig.from_yaml(config_path)

    assert config.child_id == "emma"
    assert config.child_name == "Emma"
    assert config.agent_name == "Lumi"
    assert config.max_attempts == 2


def test_runtime_material_review_creates_exercises_only_after_parent_answers(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_id="kid-1", child_name="Alex")

    material = runtime.add_material_set({
        "title": "Bruchrechnung Arbeitsblatt",
        "subject": "math",
        "source_type": "text",
        "text_excerpt": "1/2 + 1/4?\n3/5 von 20?",
        "task_candidates": ["1/2 + 1/4?", "3/5 von 20?"],
        "notes": "parent pasted worksheet text",
    })
    refused = runtime.approve_material_tasks(material["id"], expected_answers=[])

    assert refused["status"] == "missing_answers"
    assert runtime.exercises() == []

    approved = runtime.approve_material_tasks(material["id"], expected_answers=["3/4", "12"], requested_by="parent")

    assert approved["status"] == "approved"
    assert approved["material"]["status"] == "approved"
    assert approved["created"] == 2
    exercises = runtime.exercises()
    assert [row["prompt"] for row in exercises] == ["1/2 + 1/4?", "3/5 von 20?"]
    assert [row["answer"] for row in exercises] == ["3/4", "12"]
    assert {row["metadata"]["material_set_id"] for row in exercises} == {material["id"]}
    assert runtime.material_status()["pending_review"] == 0


def test_config_defaults_unset_hermes_home_placeholder_to_user_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
storage:
  data_dir: "${HERMES_HOME}/family/learnbuddy"
""".strip(),
        encoding="utf-8",
    )

    config = LearnBuddyConfig.from_yaml(config_path)

    assert config.resolved_storage_dir() == tmp_path / ".hermes" / "family" / "learnbuddy"


def test_runtime_opens_exercise_queues_second_and_promotes_after_exhaustion(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3, child_id="kid-1", child_name="Alex", agent_name="BuddyBot")
    first = runtime.add_exercise({
        "subject": "math",
        "type": "calculation",
        "prompt": "What is 2 + 2?",
        "answer": "4",
    })
    second = runtime.add_exercise({
        "subject": "english",
        "type": "vocabulary",
        "prompt": "Translate: Hund",
        "answer": "dog",
        "aliases": ["a dog"],
    })

    opened = runtime.open_exercise(first["id"], mode="manual", requested_by="parent")
    queued = runtime.open_exercise(second["id"], mode="manual", requested_by="parent")

    assert opened["status"] == "opened"
    assert opened["session"]["child_id"] == "kid-1"
    assert opened["session"]["child_name"] == "Alex"
    assert opened["session"]["agent_name"] == "BuddyBot"
    assert queued["status"] == "queued"
    assert runtime.status()["pending"]["exercise_id"] == first["id"]
    assert len(runtime.status()["queue"]) == 1

    assert runtime.submit_answer("5")["result"] == "retry"
    assert runtime.submit_answer("6")["result"] == "retry"
    exhausted = runtime.submit_answer("7")

    assert exhausted["result"] == "exhausted"
    assert exhausted["attempts"] == 3
    assert exhausted["correct"] is False
    assert "Alle 3 Versuche" in exhausted["feedback"]
    assert exhausted["promoted_session"]["exercise_id"] == second["id"]
    assert runtime.status()["pending"]["exercise_id"] == second["id"]
    assert runtime.status()["queue"] == []

    correct = runtime.submit_answer("A dog")
    assert correct["result"] == "correct"
    assert correct["correct"] is True
    assert correct["promoted_session"] is None
    assert runtime.status()["pending"] is None


def test_runtime_limits_followup_queue_without_losing_pending(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", queue_max=1)
    first = runtime.add_exercise({"subject": "math", "prompt": "1 + 1?", "answer": "2"})
    second = runtime.add_exercise({"subject": "math", "prompt": "2 + 2?", "answer": "4"})
    third = runtime.add_exercise({"subject": "math", "prompt": "3 + 3?", "answer": "6"})

    opened = runtime.open_exercise(first["id"])
    queued = runtime.open_exercise(second["id"])
    full = runtime.open_exercise(third["id"])

    assert opened["status"] == "opened"
    assert queued["status"] == "queued"
    assert full["status"] == "queue_full"
    assert full["queue_count"] == 1
    assert full["queue_max"] == 1
    state = runtime.status()
    assert state["pending"]["exercise_id"] == first["id"]
    assert [item["exercise_id"] for item in state["queue"]] == [second["id"]]
    assert all(row["exercise_id"] != third["id"] for row in runtime.sessions())


def test_runtime_tracks_pending_child_delivery_status(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy")
    exercise = runtime.add_exercise({"prompt": "100 + 101?", "answer": "201"})

    opened = runtime.open_exercise(exercise["id"])

    assert opened["session"]["delivery"]["child"]["status"] == "not_attempted"
    updated = runtime.mark_pending_delivery({
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "child",
        "message_id": None,
        "error": None,
    })
    assert updated["delivery"]["child"]["status"] == "dry_run"
    assert updated["delivery"]["child"]["attempts"] == 1
    assert updated["delivery"]["child"]["delivered_at"]
    assert runtime.status()["pending"]["delivery"]["child"]["status"] == "dry_run"



def test_runtime_parent_report_uses_synthetic_sessions_and_answers(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3, child_name="Alex", agent_name="BuddyBot")
    first = runtime.add_exercise({"subject": "math", "prompt": "3 + 4?", "answer": "7"})
    second = runtime.add_exercise({"subject": "english", "prompt": "Translate: Katze", "answer": "cat"})

    runtime.open_exercise(first["id"])
    runtime.submit_answer("7")
    runtime.open_exercise(second["id"])
    runtime.submit_answer("dog")
    runtime.submit_answer("mouse")
    runtime.submit_answer("bird")

    report = runtime.parent_report()

    assert report["answers"] == 4
    assert report["correct"] == 1
    assert report["exhausted"] == 1
    assert report["subjects"] == {"math": {"answers": 1, "correct": 1}, "english": {"answers": 3, "correct": 0}}
    assert report["child_name"] == "Alex"
    assert report["agent_name"] == "BuddyBot"
    assert "Alex" in report["text"]
    assert "BuddyBot" in report["text"]
    assert "1/4 richtig" in report["text"]


def test_runtime_grades_parent_created_multi_math_batch(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3)
    exercise = runtime.add_exercise({
        "subject": "math",
        "type": "short",
        "prompt": "Rechne bitte:\n1 + 1 = ?\n10 + 10 = ?\n33 + 33 = ?",
        "answer": "2, 20, 66",
    })

    runtime.open_exercise(exercise["id"])
    result = runtime.submit_answer("2\n20\n66")

    assert result["result"] == "correct"
    assert result["correct"] is True
    assert result["metadata"]["score"] == 3
    assert result["metadata"]["total"] == 3
    assert runtime.status()["pending"] is None


def test_runtime_records_parent_help_requests(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_id="kid-help", child_name="Alex", agent_name="BuddyBot")

    request = runtime.create_parent_help_request(
        "Alex hängt bei Brüchen fest.",
        subject="math",
        urgent=True,
        requested_by="child",
    )

    assert request["id"].startswith("help-")
    assert request["child_id"] == "kid-help"
    assert request["subject"] == "math"
    assert request["urgent"] is True
    assert request["status"] == "open"
    assert "Dringende Elternhilfe" in request["text"]
    assert "Alex hängt" in request["text"]
    assert runtime.help_requests() == [request]


def test_runtime_parent_daily_report_filters_to_local_day(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_name="Alex", agent_name="BuddyBot")
    yesterday = runtime.add_exercise({"subject": "math", "prompt": "1 + 1?", "answer": "2"})
    today = runtime.add_exercise({"subject": "german", "prompt": "Artikel von Baum?", "answer": "der"})

    runtime.open_exercise(yesterday["id"], timestamp="2026-05-26T20:00:00+00:00")
    runtime.submit_answer("2", timestamp="2026-05-26T20:01:00+00:00")
    runtime.open_exercise(today["id"], timestamp="2026-05-27T08:00:00+00:00")
    runtime.submit_answer("die", timestamp="2026-05-27T08:01:00+00:00")

    report = runtime.parent_daily_report(now="2026-05-27T21:00:00+02:00", timezone_name="Europe/Berlin")

    assert report["date"] == "2026-05-27"
    assert report["answers"] == 1
    assert report["answer_attempts"] == 1
    assert report["sessions_started"] == 1
    assert report["correct"] == 0
    assert report["subjects"] == {"german": {"answers": 1, "correct": 0}}
    assert "Tagesstatus" in report["text"]
    assert "Heute neu gestartete Aufgaben: 1" in report["text"]
    assert "0/1 Aufgaben final richtig" in report["text"]
    assert "Artikel von Baum?" in report["text"]
    assert "Alex: die" in report["text"]


def test_runtime_parent_daily_report_includes_attempt_history(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3, child_name="Alex", agent_name="BuddyBot")
    retried = runtime.add_exercise({"subject": "german", "prompt": "Artikel von Baum?", "answer": "der"})

    runtime.open_exercise(retried["id"], timestamp="2026-05-27T07:01:00+02:00")
    runtime.submit_answer("die", timestamp="2026-05-27T07:02:00+02:00")
    runtime.submit_answer("das", timestamp="2026-05-27T07:03:00+02:00")

    report = runtime.parent_daily_report(now="2026-05-27T21:00:00+02:00", timezone_name="Europe/Berlin")

    assert report["sessions_started"] == 1
    assert report["answers"] == 1
    assert report["answer_attempts"] == 2
    assert "Heute neu gestartete Aufgaben: 1" in report["text"]
    assert "Antworten/Versuche insgesamt: 2" in report["text"]
    assert "Vorherige Versuche: die" in report["text"]
    assert "Alex: das" in report["text"]
    assert "Antworten: noch keine abgegeben" not in report["text"]


def test_runtime_parent_automation_pause_today_and_resume(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_name="Alex")

    paused = runtime.set_parent_automation("pause_today", now="2026-05-27T10:00:00+02:00", timezone_name="Europe/Berlin", reason="Familientag")

    assert paused["status"] == "paused"
    assert paused["pause_date"] == "2026-05-27"
    assert paused["reason"] == "Familientag"
    assert runtime.parent_automation_status(now="2026-05-27T20:00:00+02:00", timezone_name="Europe/Berlin")["paused"] is True
    assert runtime.parent_automation_status(now="2026-05-28T08:00:00+02:00", timezone_name="Europe/Berlin")["paused"] is False

    resumed = runtime.set_parent_automation("resume", now="2026-05-27T11:00:00+02:00", timezone_name="Europe/Berlin")
    assert resumed["status"] == "active"
    assert runtime.parent_automation_status(now="2026-05-27T20:00:00+02:00", timezone_name="Europe/Berlin")["paused"] is False


def test_runtime_creates_and_controls_active_learning_plan(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_id="kid-plan", child_name="Alex", agent_name="BuddyBot")

    created = runtime.create_learning_plan(
        {
            "title": "Brüche festigen",
            "subjects": ["math", "german"],
            "focus": ["Brüche", "Lesen"],
            "daily_goal": 2,
            "created_by": "parent",
        }
    )

    assert created["status"] == "active"
    assert created["id"].startswith("plan-")
    assert created["child_id"] == "kid-plan"
    assert created["title"] == "Brüche festigen"
    assert created["subjects"] == ["math", "german"]
    assert created["focus"] == ["Brüche", "Lesen"]
    assert created["daily_goal"] == 2
    status = runtime.learning_plan_status()
    assert status["active_plan"]["id"] == created["id"]
    assert status["plans"] == [created]
    assert (tmp_path / "learnbuddy" / "plans.jsonl").exists()
    assert (tmp_path / "learnbuddy" / "plan-state.json").exists()

    paused = runtime.set_learning_plan("pause", plan_id=created["id"], reason="Wochenende")
    assert paused["status"] == "paused"
    assert paused["reason"] == "Wochenende"
    assert runtime.learning_plan_status()["active_plan"]["status"] == "paused"

    resumed = runtime.set_learning_plan("resume", plan_id=created["id"])
    assert resumed["status"] == "active"

    completed = runtime.set_learning_plan("complete", plan_id=created["id"], reason="Ziel erreicht")
    assert completed["status"] == "completed"
    assert runtime.learning_plan_status()["active_plan"] is None


def test_runtime_dispatches_next_exercise_from_active_learning_plan(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy")
    math = runtime.add_exercise({"subject": "math", "prompt": "1 + 1?", "answer": "2"})
    english = runtime.add_exercise({"subject": "english", "prompt": "Translate: Hund", "answer": "dog"})
    plan = runtime.create_learning_plan({"title": "Englisch üben", "subjects": ["english"], "daily_goal": 1})

    result = runtime.dispatch_learning_plan(now="2026-05-28T10:00:00+02:00")

    assert result["status"] == "opened"
    assert result["plan"]["id"] == plan["id"]
    assert result["exercise"]["id"] == english["id"]
    assert result["exercise"]["id"] != math["id"]
    assert result["session"]["source"] == "learning_plan"
    assert result["session"]["plan_id"] == plan["id"]
    assert runtime.status()["pending"]["exercise_id"] == english["id"]


def test_runtime_learning_plan_respects_pending_pause_and_daily_goal(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy")
    first = runtime.add_exercise({"subject": "math", "prompt": "1 + 1?", "answer": "2"})
    second = runtime.add_exercise({"subject": "math", "prompt": "2 + 2?", "answer": "4"})
    plan = runtime.create_learning_plan({"title": "Mathe", "subjects": ["math"], "daily_goal": 1})

    opened = runtime.dispatch_learning_plan(now="2026-05-28T10:00:00+02:00")
    assert opened["status"] == "opened"
    assert opened["exercise"]["id"] == first["id"]
    assert runtime.dispatch_learning_plan(now="2026-05-28T10:05:00+02:00")["status"] == "pending_exists"
    runtime.submit_answer("2", timestamp="2026-05-28T10:06:00+02:00")
    limit = runtime.dispatch_learning_plan(now="2026-05-28T11:00:00+02:00")
    assert limit["status"] == "plan_daily_goal_reached"
    assert limit["daily_goal"] == 1

    runtime.set_learning_plan("pause", plan_id=plan["id"], reason="Pause")
    paused = runtime.dispatch_learning_plan(now="2026-05-29T10:00:00+02:00")
    assert paused["status"] == "plan_paused"
    assert paused["plan"]["id"] == plan["id"]
    assert second["id"] not in [row["exercise_id"] for row in runtime.sessions()]


def test_runtime_plans_pending_child_reminder_with_open_prompt(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_name="Alex", agent_name="BuddyBot")
    exercise = runtime.add_exercise({"subject": "math", "prompt": "Was ist 12 + 8?", "answer": "20"})
    runtime.open_exercise(exercise["id"], timestamp="2026-05-28T06:00:00+00:00")

    reminder = runtime.pending_reminder_plan(now="2026-05-29T08:30:00+02:00", timezone_name="Europe/Berlin")

    assert reminder["status"] == "due"
    assert reminder["session_id"] == runtime.status()["pending"]["id"]
    assert reminder["child"]["stage"] == "24h"
    assert reminder["child"]["recipient"] == "child"
    assert "Alex" in reminder["child"]["text"]
    assert "Mathe" in reminder["child"]["text"]
    assert "Was ist 12 + 8?" in reminder["child"]["text"]
    assert reminder["parent"] is None


def test_runtime_pending_reminder_records_success_and_escalates_parent_once(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", child_name="Alex", agent_name="BuddyBot")
    first = runtime.add_exercise({"subject": "math", "prompt": "Was ist 12 + 8?", "answer": "20"})
    second = runtime.add_exercise({"subject": "german", "prompt": "Artikel von Baum?", "answer": "der"})
    runtime.open_exercise(first["id"], timestamp="2026-05-28T06:00:00+00:00")
    runtime.open_exercise(second["id"], timestamp="2026-05-28T06:05:00+00:00")

    first_plan = runtime.pending_reminder_plan(now="2026-05-29T08:30:00+02:00", timezone_name="Europe/Berlin")
    runtime.mark_pending_reminder_sent(first_plan, child_delivery={"status": "dry_run", "adapter": "dry_run", "target": "child"})
    duplicate = runtime.pending_reminder_plan(now="2026-05-29T18:00:00+02:00", timezone_name="Europe/Berlin")
    second_stage = runtime.pending_reminder_plan(now="2026-05-30T08:30:00+02:00", timezone_name="Europe/Berlin")

    assert duplicate["status"] == "not_due"
    assert duplicate["reason"] == "already_reminded_today"
    assert second_stage["status"] == "due"
    assert second_stage["child"]["stage"] == "48h"
    runtime.mark_pending_reminder_sent(second_stage, child_delivery={"status": "dry_run", "adapter": "dry_run", "target": "child"})

    escalation = runtime.pending_reminder_plan(now="2026-05-31T08:30:00+02:00", timezone_name="Europe/Berlin")
    assert escalation["status"] == "due"
    assert escalation["child"] is None
    assert escalation["parent"]["stage"] == "72h"
    assert escalation["parent"]["recipient"] == "parent"
    assert "Was ist 12 + 8?" in escalation["parent"]["text"]
    assert "Warteschlange: 1" in escalation["parent"]["text"]
    runtime.mark_pending_reminder_sent(escalation, parent_delivery={"status": "dry_run", "adapter": "dry_run", "target": "parent"})

    repeated_escalation = runtime.pending_reminder_plan(now="2026-06-01T08:30:00+02:00", timezone_name="Europe/Berlin")
    assert repeated_escalation["status"] == "not_due"
    assert repeated_escalation["reason"] == "stages_already_sent"
    assert (tmp_path / "learnbuddy" / "pending-reminder-state.json").exists()
