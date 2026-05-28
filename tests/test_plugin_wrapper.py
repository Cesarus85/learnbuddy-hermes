import importlib.util
import json
from pathlib import Path


def load_plugin():
    path = Path("plugins/learnbuddy-learning/__init__.py")
    spec = importlib.util.spec_from_file_location("learnbuddy_learning_plugin", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plugin_tools_use_isolated_data_dir_and_return_json(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "plugin-data"

    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "data_dir": str(data_dir),
        "subject": "math",
        "prompt": "1 + 1?",
        "answer": "2",
    }))
    opened = json.loads(plugin.learnbuddy_next_exercise({"data_dir": str(data_dir), "exercise_id": queued["exercise"]["id"]}))
    answer = json.loads(plugin.learnbuddy_submit_answer({"data_dir": str(data_dir), "answer": "2"}))
    status = json.loads(plugin.learnbuddy_learning_status({"data_dir": str(data_dir)}))

    assert opened["status"] == "opened"
    assert answer["result"] == "correct"
    assert status["pending"] is None
    assert (data_dir / "exercises.jsonl").exists()
    assert (data_dir / "answers.jsonl").exists()


def test_plugin_learning_plan_tools_and_dispatch_use_active_plan(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "plugin-plan-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    math = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "1 + 1?",
        "answer": "2",
    }))["exercise"]
    english = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "english",
        "prompt": "Translate: Hund",
        "answer": "dog",
    }))["exercise"]

    created = json.loads(plugin.learnbuddy_create_learning_plan({
        "config_path": str(config_path),
        "title": "English focus",
        "subjects": ["english"],
        "focus": ["vocabulary"],
        "daily_goal": 1,
    }))
    status = json.loads(plugin.learnbuddy_learning_plan_status({"config_path": str(config_path)}))
    dispatched = json.loads(plugin.learnbuddy_dispatch_plan({"config_path": str(config_path), "now": "2026-05-28T10:00:00+02:00"}))

    assert created["status"] == "active"
    assert status["active_plan"]["id"] == created["plan"]["id"]
    assert dispatched["status"] == "opened"
    assert dispatched["plan"]["id"] == created["plan"]["id"]
    assert dispatched["exercise"]["id"] == english["id"]
    assert dispatched["exercise"]["id"] != math["id"]
    assert dispatched["delivery"]["status"] == "dry_run"
    assert dispatched["session"]["source"] == "learning_plan"

    controlled = json.loads(plugin.learnbuddy_control_learning_plan({
        "config_path": str(config_path),
        "action": "pause",
        "reason": "break",
    }))
    assert controlled["status"] == "paused"


def test_child_submit_answer_notifies_parent_by_default(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "child-answer-notify"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
child:
  display_name: Alex
agent:
  name: BuddyBot
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "1 + 1?",
        "answer": "2",
    }))
    plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]})

    result = json.loads(plugin.learnbuddy_child_submit_answer({"config_path": str(config_path), "answer": "2"}))

    assert result["result"] == "correct"
    assert result["parent_delivery"]["status"] == "dry_run"
    assert result["parent_delivery"]["target"] == "parent"


def test_parent_answer_status_reports_recent_completed_answer_and_parent_delivery(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "parent-answer-status"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
child:
  display_name: Alex
agent:
  name: BuddyBot
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 7 + 4?",
        "answer": "11",
    }))
    plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]})
    answer = json.loads(plugin.learnbuddy_child_submit_answer({"config_path": str(config_path), "answer": "11"}))

    status = json.loads(plugin.learnbuddy_parent_answer_status({"config_path": str(config_path)}))

    assert answer["result"] == "correct"
    assert status["status"] == "ok"
    assert status["pending"] is None
    assert status["answers"] == 1
    latest = status["latest_answer"]
    assert latest["prompt"] == "Was ist 7 + 4?"
    assert latest["answer"] == "11"
    assert latest["result"] == "correct"
    assert latest["correct"] is True
    assert latest["attempts"] == 1
    assert latest["parent_delivery"]["status"] == "dry_run"
    assert "Alex hat geantwortet" in status["text"]
    assert "Was ist 7 + 4?" in status["text"]


def test_plugin_accepts_config_file_for_child_and_agent_identity(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "configured-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
child:
  id: kid-2
  display_name: Jamie
agent:
  name: LernKumpel
safety:
  max_attempts: 2
storage:
  data_dir: {data_dir}
""".strip(),
        encoding="utf-8",
    )

    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "english",
        "prompt": "Translate: Katze",
        "answer": "cat",
    }))
    opened = json.loads(plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]}))
    first_wrong = json.loads(plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "dog"}))
    exhausted = json.loads(plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "mouse"}))
    report = json.loads(plugin.learnbuddy_parent_report({"config_path": str(config_path)}))

    assert opened["session"]["child_id"] == "kid-2"
    assert opened["session"]["child_name"] == "Jamie"
    assert opened["session"]["agent_name"] == "LernKumpel"
    assert first_wrong["result"] == "retry"
    assert exhausted["result"] == "exhausted"
    assert exhausted["max_attempts"] == 2
    assert report["child_name"] == "Jamie"
    assert report["agent_name"] == "LernKumpel"


def test_next_exercise_can_dry_run_deliver_opened_prompt(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "delivery-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 2 + 2?",
        "answer": "4",
    }))

    opened = json.loads(plugin.learnbuddy_next_exercise({
        "config_path": str(config_path),
        "exercise_id": queued["exercise"]["id"],
        "deliver": True,
    }))

    assert opened["status"] == "opened"
    assert opened["delivery"] == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "child",
        "message_id": None,
        "error": None,
    }


def test_plugin_uses_env_config_path_when_arg_omitted(tmp_path, monkeypatch):
    plugin = load_plugin()
    data_dir = tmp_path / "env-config-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
child:
  id: env-child
  display_name: Env Learner
agent:
  name: EnvBuddy
storage:
  data_dir: {data_dir}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("LEARNBUDDY_CONFIG_PATH", str(config_path))

    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "subject": "math",
        "prompt": "3 + 4?",
        "answer": "7",
    }))
    opened = json.loads(plugin.learnbuddy_next_exercise({"exercise_id": queued["exercise"]["id"]}))

    assert opened["session"]["child_id"] == "env-child"
    assert opened["session"]["child_name"] == "Env Learner"
    assert opened["session"]["agent_name"] == "EnvBuddy"


def test_create_and_send_exercise_queues_opens_and_delivers(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "create-send-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    result = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "5 + 5?",
        "answer": "10",
    }))

    assert result["status"] == "sent"
    assert result["exercise"]["prompt"] == "5 + 5?"
    assert result["opened"]["status"] == "opened"
    assert result["opened"]["delivery"] == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "child",
        "message_id": None,
        "error": None,
    }


def test_create_and_send_refuses_when_followup_queue_is_full_without_storing_exercise(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "queue-full-create-send-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  queue_max: 1
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    first = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "1 + 1?",
        "answer": "2",
    }))
    second = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "2 + 2?",
        "answer": "4",
    }))
    full = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "should not persist",
        "answer": "6",
    }))

    assert first["status"] == "sent"
    assert second["opened"]["status"] == "queued"
    assert full["status"] == "queue_full"
    assert full["queue_count"] == 1
    exercises_text = (data_dir / "exercises.jsonl").read_text(encoding="utf-8")
    assert "should not persist" not in exercises_text


def test_dispatch_plan_opens_and_delivers_scheduled_exercise(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "dispatch-plan-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "6 + 7?",
        "answer": "13",
    }))

    result = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "exercise_id": queued["exercise"]["id"],
        "now": "2026-05-26T10:00:00+02:00",
    }))

    assert result["status"] == "opened"
    assert result["delivery_status"] == "sent"
    assert result["delivery"]["status"] == "dry_run"
    assert result["session"]["mode"] == "auto"
    assert result["session"]["requested_by"] == "system"


def test_schedule_exercise_parent_tool_and_dispatch_due_delivery(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "scheduled-plugin-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    scheduled = json.loads(plugin.learnbuddy_schedule_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "10 + 20?",
        "answer": "30",
        "due_at": "2026-05-28T10:30:00+02:00",
    }))
    assert scheduled["status"] == "scheduled"

    before_due = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "now": "2026-05-28T10:29:00+02:00",
    }))
    assert before_due["status"] == "no_due_scheduled_exercise"

    dispatched = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "now": "2026-05-28T10:30:00+02:00",
    }))

    assert dispatched["status"] == "opened"
    assert dispatched["scheduled"]["id"] == scheduled["scheduled"]["id"]
    assert dispatched["delivery_status"] == "sent"
    assert dispatched["delivery"]["status"] == "dry_run"
    assert dispatched["session"]["source"] == "scheduled_exercise"


def test_plugin_scheduled_exercise_bypasses_auto_limit_after_pending_answer(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "scheduled-plugin-after-pending-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "english",
        "prompt": "Was heißt Löffel auf Englisch?",
        "answer": "spoon",
    }))
    first = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "exercise_id": queued["exercise"]["id"],
        "now": "2026-05-28T10:00:00+02:00",
    }))
    assert first["status"] == "opened"

    scheduled = json.loads(plugin.learnbuddy_schedule_exercise({
        "config_path": str(config_path),
        "subject": "english",
        "prompt": "Was heißt Auto auf Englisch?",
        "answer": "car",
        "due_at": "2026-05-28T10:30:00+02:00",
    }))
    blocked = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "now": "2026-05-28T10:31:00+02:00",
    }))
    assert blocked["status"] == "pending_exists"

    answer = json.loads(plugin.learnbuddy_child_submit_answer({"config_path": str(config_path), "answer": "spoon"}))
    assert answer["result"] == "correct"
    dispatched = json.loads(plugin.learnbuddy_dispatch_plan({
        "config_path": str(config_path),
        "now": "2026-05-28T10:32:00+02:00",
    }))

    assert dispatched["status"] == "opened"
    assert dispatched["scheduled"]["id"] == scheduled["scheduled"]["id"]
    assert dispatched["session"]["source"] == "scheduled_exercise"
    assert dispatched["delivery_status"] == "sent"


def test_plugin_loads_default_env_file_before_delivery(tmp_path, monkeypatch):
    plugin = load_plugin()
    data_dir = tmp_path / "env-file-data"
    config_path = tmp_path / "learnbuddy.yaml"
    env_file = tmp_path / "learnbuddy.env"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: telegram
  child:
    type: telegram
    bot_token_env: CHILD_BOT
    allowed_chat_ids_env: CHILD_CHAT
  parents:
    - type: telegram
      bot_token_env: PARENT_BOT
      target_env: PARENT_CHAT
""".strip(),
        encoding="utf-8",
    )
    env_file.write_text("CHILD_BOT=fake-child\nCHILD_CHAT=1\nPARENT_BOT=fake-parent\nPARENT_CHAT=2\n", encoding="utf-8")
    monkeypatch.setenv("LEARNBUDDY_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("LEARNBUDDY_ENV_FILE", str(env_file))
    for name in ["CHILD_BOT", "CHILD_CHAT", "PARENT_BOT", "PARENT_CHAT"]:
        monkeypatch.delenv(name, raising=False)

    class FakeResult:
        def to_dict(self):
            return {"status": "fake_sent", "adapter": "fake", "target": "parent", "message_id": "m1", "error": None}

    class FakeAdapter:
        def deliver_parent(self, message):
            assert message.text.startswith("LearnBuddy Status")
            return FakeResult()

    def fake_factory(config, *, recipient="child"):
        assert recipient == "parent"
        assert __import__("os").getenv("PARENT_BOT") == "fake-parent"
        assert __import__("os").getenv("PARENT_CHAT") == "2"
        return FakeAdapter()

    monkeypatch.setattr(plugin, "delivery_adapter_from_config", fake_factory)

    report = json.loads(plugin.learnbuddy_parent_report({"notify": True}))

    assert report["notification"]["status"] == "fake_sent"


def test_registered_tools_expose_guided_parent_command_schemas():
    plugin = load_plugin()

    class FakeContext:
        def __init__(self):
            self.tools = {}

        def register_tool(self, *, name, schema, toolset, handler):
            self.tools[name] = {"schema": schema, "toolset": toolset, "handler": handler}

    ctx = FakeContext()
    plugin.register(ctx)

    assert set(ctx.tools) == {
        "learnbuddy_queue_exercise",
        "learnbuddy_next_exercise",
        "learnbuddy_create_and_send_exercise",
        "learnbuddy_deliver_pending_exercise",
        "learnbuddy_schedule_exercise",
        "learnbuddy_dispatch_plan",
        "learnbuddy_parent_command_contracts",
        "learnbuddy_create_learning_plan",
        "learnbuddy_learning_plan_status",
        "learnbuddy_control_learning_plan",
        "learnbuddy_submit_answer",
        "learnbuddy_learning_status",
        "learnbuddy_parent_answer_status",
        "learnbuddy_parent_report",
        "learnbuddy_daily_parent_status",
        "learnbuddy_weekly_parent_status",
        "learnbuddy_parent_automation_control",
        "learnbuddy_parent_help_request",
        "learnbuddy_child_submit_answer",
        "learnbuddy_child_status",
        "learnbuddy_child_repeat_pending",
        "learnbuddy_child_request_next_exercise",
        "learnbuddy_child_request_parent_help",
    }
    create_schema = ctx.tools["learnbuddy_create_and_send_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_create_and_send_exercise"]["toolset"] == "learnbuddy_learning"
    assert create_schema["additionalProperties"] is False
    assert create_schema["required"] == ["prompt"]
    assert {tuple(item["required"]) for item in create_schema["anyOf"]} == {("answer",), ("expected_answers",)}
    assert create_schema["properties"]["subject"]["enum"] == ["math", "german", "english", "general"]
    assert create_schema["properties"]["answer"]["description"].startswith("Canonical expected answer")
    assert "Do not call" in ctx.tools["learnbuddy_create_and_send_exercise"]["schema"]["description"]
    assert "expected answer" in ctx.tools["learnbuddy_create_and_send_exercise"]["schema"]["description"]
    repair_schema = ctx.tools["learnbuddy_deliver_pending_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_deliver_pending_exercise"]["toolset"] == "learnbuddy_learning"
    assert repair_schema["additionalProperties"] is False
    assert repair_schema["properties"]["force"]["default"] is False

    dispatch_schema = ctx.tools["learnbuddy_dispatch_plan"]["schema"]["parameters"]
    schedule_schema = ctx.tools["learnbuddy_schedule_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_schedule_exercise"]["toolset"] == "learnbuddy_learning"
    assert schedule_schema["additionalProperties"] is False
    assert schedule_schema["required"] == ["prompt", "due_at"]
    assert {tuple(item["required"]) for item in schedule_schema["anyOf"]} == {("answer",), ("expected_answers",)}
    assert "ISO timestamp" in schedule_schema["properties"]["due_at"]["description"]
    assert ctx.tools["learnbuddy_dispatch_plan"]["toolset"] == "learnbuddy_learning"
    assert dispatch_schema["additionalProperties"] is False
    assert dispatch_schema["properties"]["subject"]["enum"] == ["math", "german", "english", "general"]

    contracts_schema = ctx.tools["learnbuddy_parent_command_contracts"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_parent_command_contracts"]["toolset"] == "learnbuddy_learning"
    assert contracts_schema["additionalProperties"] is False
    assert "Parent command contract" in ctx.tools["learnbuddy_parent_command_contracts"]["schema"]["description"]

    plan_create_schema = ctx.tools["learnbuddy_create_learning_plan"]["schema"]["parameters"]
    plan_status_schema = ctx.tools["learnbuddy_learning_plan_status"]["schema"]["parameters"]
    plan_control_schema = ctx.tools["learnbuddy_control_learning_plan"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_create_learning_plan"]["toolset"] == "learnbuddy_learning"
    assert ctx.tools["learnbuddy_learning_plan_status"]["toolset"] == "learnbuddy_learning"
    assert ctx.tools["learnbuddy_control_learning_plan"]["toolset"] == "learnbuddy_learning"
    assert plan_create_schema["required"] == ["title"]
    assert plan_create_schema["additionalProperties"] is False
    assert plan_status_schema["additionalProperties"] is False
    assert plan_control_schema["required"] == ["action"]
    assert plan_control_schema["properties"]["action"]["enum"] == ["pause", "resume", "complete", "cancel"]

    answer_schema = ctx.tools["learnbuddy_submit_answer"]["schema"]["parameters"]
    assert answer_schema["required"] == ["answer"]
    assert answer_schema["properties"]["input_mode"]["enum"] == ["text", "audio"]

    report_schema = ctx.tools["learnbuddy_parent_report"]["schema"]["parameters"]
    answer_status_schema = ctx.tools["learnbuddy_parent_answer_status"]["schema"]["parameters"]
    assert answer_status_schema["properties"]["limit"]["default"] == 3
    assert "recent answer" in ctx.tools["learnbuddy_parent_answer_status"]["schema"]["description"].lower()
    assert report_schema["properties"]["notify"]["default"] is False
    daily_schema = ctx.tools["learnbuddy_daily_parent_status"]["schema"]["parameters"]
    weekly_schema = ctx.tools["learnbuddy_weekly_parent_status"]["schema"]["parameters"]
    automation_schema = ctx.tools["learnbuddy_parent_automation_control"]["schema"]["parameters"]
    assert daily_schema["properties"]["notify"]["default"] is False
    assert daily_schema["properties"]["include_empty"]["default"] is False
    assert weekly_schema["properties"]["notify"]["default"] is False
    assert weekly_schema["properties"]["include_empty"]["default"] is False
    assert ctx.tools["learnbuddy_weekly_parent_status"]["toolset"] == "learnbuddy_learning"
    assert "weekly parent report" in ctx.tools["learnbuddy_weekly_parent_status"]["schema"]["description"].lower()
    assert automation_schema["required"] == ["action"]
    assert automation_schema["properties"]["action"]["enum"] == ["status", "pause_today", "resume"]

    help_schema = ctx.tools["learnbuddy_parent_help_request"]["schema"]["parameters"]
    assert help_schema["required"] == ["reason"]
    assert help_schema["additionalProperties"] is False
    assert help_schema["properties"]["notify"]["default"] is False
    assert "external/non-learning" in ctx.tools["learnbuddy_parent_help_request"]["schema"]["description"]

    assert ctx.tools["learnbuddy_child_submit_answer"]["toolset"] == "learnbuddy_child"
    assert ctx.tools["learnbuddy_child_status"]["toolset"] == "learnbuddy_child"
    repeat_schema = ctx.tools["learnbuddy_child_repeat_pending"]["schema"]["parameters"]
    child_next_schema = ctx.tools["learnbuddy_child_request_next_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_child_repeat_pending"]["toolset"] == "learnbuddy_child"
    assert ctx.tools["learnbuddy_child_request_next_exercise"]["toolset"] == "learnbuddy_child"
    assert repeat_schema["additionalProperties"] is False
    assert child_next_schema["additionalProperties"] is False
    assert child_next_schema["properties"]["notify_parent"]["default"] is True
    assert "exactly one next exercise" in ctx.tools["learnbuddy_child_request_next_exercise"]["schema"]["description"]
    child_help_schema = ctx.tools["learnbuddy_child_request_parent_help"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_child_request_parent_help"]["toolset"] == "learnbuddy_child"
    assert child_help_schema["required"] == ["reason"]
    assert "notify" not in child_help_schema["properties"]


def test_parent_command_contracts_cover_parent_telegram_operations():
    plugin = load_plugin()

    contracts = json.loads(plugin.learnbuddy_parent_command_contracts({}))

    assert contracts["status"] == "ok"
    operations = {item["operation"]: item for item in contracts["contracts"]}
    assert set(operations) == {"current_status", "answer_status", "report", "daily_status", "weekly_status", "automation_control", "resend_pending", "dispatch_plan", "learning_plan", "create_and_send_exercise", "schedule_exercise"}
    assert operations["current_status"]["tool"] == "learnbuddy_learning_status"
    assert "Was ist offen?" in operations["current_status"]["examples"]
    assert operations["answer_status"]["tool"] == "learnbuddy_parent_answer_status"
    assert "Hat Learner geantwortet?" in operations["answer_status"]["examples"]
    assert operations["answer_status"]["policy"].startswith("Read-only")
    assert operations["report"]["tool"] == "learnbuddy_parent_report"
    assert operations["report"]["notify_default"] is False
    assert operations["daily_status"]["tool"] == "learnbuddy_daily_parent_status"
    assert operations["daily_status"]["policy_bounded"] is True
    assert operations["weekly_status"]["tool"] == "learnbuddy_weekly_parent_status"
    assert operations["weekly_status"]["policy_bounded"] is True
    assert "Wochenbericht" in operations["weekly_status"]["examples"]
    assert operations["automation_control"]["tool"] == "learnbuddy_parent_automation_control"
    assert "heute pausieren" in operations["automation_control"]["examples"]
    assert operations["resend_pending"]["tool"] == "learnbuddy_deliver_pending_exercise"
    assert operations["resend_pending"]["args"] == {"force": True}
    assert operations["dispatch_plan"]["tool"] == "learnbuddy_dispatch_plan"
    assert operations["dispatch_plan"]["policy_bounded"] is True
    assert operations["learning_plan"]["tool"] == "learnbuddy_create_learning_plan / learnbuddy_learning_plan_status / learnbuddy_control_learning_plan"
    assert operations["learning_plan"]["policy_bounded"] is True
    assert "existing exercises" in operations["learning_plan"]["policy"]
    assert operations["create_and_send_exercise"]["tool"] == "learnbuddy_create_and_send_exercise"
    assert operations["create_and_send_exercise"]["requires"] == ["prompt", "answer_or_expected_answers"]
    assert "Frage Learner folgende Aufgaben" in operations["create_and_send_exercise"]["examples"]
    assert operations["schedule_exercise"]["tool"] == "learnbuddy_schedule_exercise"
    assert operations["schedule_exercise"]["requires"] == ["prompt", "answer_or_expected_answers", "due_at"]
    assert "10:30" in operations["schedule_exercise"]["examples"][0]
    assert contracts["safety"]["no_child_toolset"] is True
    assert contracts["safety"]["no_unbounded_generation"] is True


def test_daily_parent_status_and_automation_control_tools(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "daily-status-plugin"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Alex
agent:
  name: BuddyBot
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "3 + 5?",
        "answer": "8",
    }))
    plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]})
    plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "8"})

    first = json.loads(plugin.learnbuddy_daily_parent_status({
        "config_path": str(config_path),
        "notify": True,
    }))
    weekly = json.loads(plugin.learnbuddy_weekly_parent_status({
        "config_path": str(config_path),
        "notify": True,
        "now": "2026-05-31T19:00:00+02:00",
    }))
    duplicate_weekly = json.loads(plugin.learnbuddy_weekly_parent_status({
        "config_path": str(config_path),
        "notify": True,
        "now": "2026-05-31T20:00:00+02:00",
    }))
    duplicate = json.loads(plugin.learnbuddy_daily_parent_status({
        "config_path": str(config_path),
        "notify": True,
    }))
    paused = json.loads(plugin.learnbuddy_parent_automation_control({
        "config_path": str(config_path),
        "action": "pause_today",
        "reason": "Pause",
        "now": "2026-05-28T10:00:00+02:00",
    }))
    skipped = json.loads(plugin.learnbuddy_daily_parent_status({
        "config_path": str(config_path),
        "notify": True,
        "include_empty": True,
        "now": "2026-05-28T21:00:00+02:00",
    }))

    assert first["status"] == "sent"
    assert first["notification"]["status"] == "dry_run"
    assert weekly["status"] == "sent"
    assert weekly["notification"]["status"] == "dry_run"
    assert weekly["report"]["week_key"] == "2026-05-25/2026-05-31"
    assert duplicate_weekly["status"] == "already_sent"
    assert duplicate["status"] == "already_sent"
    assert paused["status"] == "paused"
    assert skipped["status"] == "automation_paused"
    assert skipped["notification"] is None


def test_create_and_send_requires_expected_answer_before_delivery(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "missing-answer"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    result = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "1 + 1 =?\n10 + 10 = ?\n33 + 33 = ?",
    }))
    status = json.loads(plugin.learnbuddy_learning_status({"config_path": str(config_path)}))

    assert result["status"] == "missing_expected_answer"
    assert "answer" in result["error"]
    assert status["pending"] is None
    assert status["queue"] == []


def test_create_and_send_multi_part_exercise_with_expected_answers_round_trips(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "multi-parent-send"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    sent = json.loads(plugin.learnbuddy_create_and_send_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "1 + 1 =?\n10 + 10 = ?\n33 + 33 = ?",
        "expected_answers": ["2", "20", "66"],
    }))
    answer = json.loads(plugin.learnbuddy_child_submit_answer({
        "config_path": str(config_path),
        "answer": "2\n20\n66",
    }))

    assert sent["status"] == "sent"
    assert sent["opened"]["delivery_status"] == "sent"
    assert answer["result"] == "correct"
    assert answer["feedback"] == "Richtig! Alle Teilaufgaben stimmen 🎉"
    assert answer["metadata"]["score"] == 3
    assert answer["metadata"]["total"] == 3


def test_child_profile_aliases_are_narrow_and_parent_help_notifies(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "child-profile-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  id: kid-help
  display_name: Alex
agent:
  name: BuddyBot
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 3 + 3?",
        "answer": "6",
    }))
    json.loads(plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]}))

    answer = json.loads(plugin.learnbuddy_child_submit_answer({"config_path": str(config_path), "answer": "6"}))
    status = json.loads(plugin.learnbuddy_child_status({"config_path": str(config_path)}))
    result = json.loads(plugin.learnbuddy_child_request_parent_help({
        "config_path": str(config_path),
        "subject": "math",
        "reason": "Alex möchte nochmal Brüche üben.",
        "urgent": True,
    }))

    assert answer["result"] == "correct"
    assert status["pending"] is None
    assert result["status"] == "created"
    request = result["help_request"]
    assert request["child_id"] == "kid-help"
    assert request["child_name"] == "Alex"
    assert request["agent_name"] == "BuddyBot"
    assert request["subject"] == "math"
    assert request["requested_by"] == "child"
    assert request["notification"] == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "parent",
        "message_id": None,
        "error": None,
    }


def test_child_profile_control_tools_repeat_and_policy_bound_next(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "child-control-tools"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Alex
agent:
  name: BuddyBot
safety:
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    first = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 4 + 4?",
        "answer": "8",
    }))
    second = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 5 + 5?",
        "answer": "10",
    }))
    json.loads(plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": first["exercise"]["id"], "deliver": True}))

    repeat = json.loads(plugin.learnbuddy_child_repeat_pending({"config_path": str(config_path)}))
    blocked_next = json.loads(plugin.learnbuddy_child_request_next_exercise({
        "config_path": str(config_path),
        "request": "Noch eine Aufgabe",
        "now": "2026-05-27T10:00:00+02:00",
    }))
    answer = json.loads(plugin.learnbuddy_child_submit_answer({"config_path": str(config_path), "answer": "8", "notify_parent": False}))
    opened_next = json.loads(plugin.learnbuddy_child_request_next_exercise({
        "config_path": str(config_path),
        "request": "Noch eine Aufgabe",
        "now": "2026-05-27T10:05:00+02:00",
    }))

    assert second["status"] == "created"
    assert repeat["command"] == "repeat"
    assert repeat["status"] == "sent"
    assert repeat["child_delivery"]["status"] == "dry_run"
    assert repeat["child_delivery"]["metadata"]["kind"] == "pending_exercise_repeat"
    assert blocked_next["command"] == "next"
    assert blocked_next["dispatch"]["status"] == "pending_exists"
    assert blocked_next["child_delivery"]["metadata"]["kind"] == "finish_pending_first"
    assert answer["result"] == "correct"
    assert opened_next["command"] == "next"
    assert opened_next["dispatch"]["status"] == "opened"
    assert opened_next["child_delivery"]["status"] == "dry_run"
    assert opened_next["child_delivery"]["metadata"]["kind"] == "child_requested_next_exercise"
    status = json.loads(plugin.learnbuddy_child_status({"config_path": str(config_path)}))
    assert status["pending"]["prompt"] == "Was ist 5 + 5?"


def test_parent_report_can_dry_run_notify_parent(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "parent-notifier-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "math",
        "prompt": "Was ist 1 + 1?",
        "answer": "2",
    }))
    json.loads(plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]}))
    json.loads(plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "2"}))

    report = json.loads(plugin.learnbuddy_parent_report({"config_path": str(config_path), "notify": True}))

    assert report["correct"] == 1
    assert report["notification"] == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "parent",
        "message_id": None,
        "error": None,
    }


def test_parent_report_notify_uses_parent_telegram_target(tmp_path, monkeypatch):
    plugin = load_plugin()
    data_dir = tmp_path / "parent-telegram-notifier-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
delivery:
  mode: telegram
  child:
    type: telegram
    bot_token_env: CHILD_BOT_TOKEN_ENV
    allowed_chat_ids_env: CHILD_CHAT_ID_ENV
  parents:
    - type: telegram
      bot_token_env: PARENT_BOT_TOKEN_ENV
      target_env: PARENT_CHAT_ID_ENV
""".strip(),
        encoding="utf-8",
    )
    for name in ["CHILD_BOT_TOKEN_ENV", "CHILD_CHAT_ID_ENV", "PARENT_BOT_TOKEN_ENV", "PARENT_CHAT_ID_ENV"]:
        monkeypatch.delenv(name, raising=False)

    report = json.loads(plugin.learnbuddy_parent_report({"config_path": str(config_path), "notify": True}))

    assert report["notification"]["status"] == "not_configured"
    assert report["notification"]["adapter"] == "telegram"
    assert report["notification"]["target"] == "PARENT_CHAT_ID_ENV"
    assert report["notification"]["error"] == "missing environment variables: PARENT_BOT_TOKEN_ENV, PARENT_CHAT_ID_ENV"
