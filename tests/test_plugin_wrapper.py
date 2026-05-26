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
        "learnbuddy_submit_answer",
        "learnbuddy_learning_status",
        "learnbuddy_parent_report",
        "learnbuddy_parent_help_request",
        "learnbuddy_child_submit_answer",
        "learnbuddy_child_status",
        "learnbuddy_child_request_parent_help",
    }
    create_schema = ctx.tools["learnbuddy_create_and_send_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_create_and_send_exercise"]["toolset"] == "learnbuddy_learning"
    assert create_schema["additionalProperties"] is False
    assert create_schema["required"] == ["prompt"]
    assert create_schema["properties"]["subject"]["enum"] == ["math", "german", "english", "general"]
    assert create_schema["properties"]["answer"]["description"].startswith("Canonical expected answer")
    assert "Do not call" in ctx.tools["learnbuddy_create_and_send_exercise"]["schema"]["description"]
    repair_schema = ctx.tools["learnbuddy_deliver_pending_exercise"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_deliver_pending_exercise"]["toolset"] == "learnbuddy_learning"
    assert repair_schema["additionalProperties"] is False
    assert repair_schema["properties"]["force"]["default"] is False

    answer_schema = ctx.tools["learnbuddy_submit_answer"]["schema"]["parameters"]
    assert answer_schema["required"] == ["answer"]
    assert answer_schema["properties"]["input_mode"]["enum"] == ["text", "audio"]

    report_schema = ctx.tools["learnbuddy_parent_report"]["schema"]["parameters"]
    assert report_schema["properties"]["notify"]["default"] is False

    help_schema = ctx.tools["learnbuddy_parent_help_request"]["schema"]["parameters"]
    assert help_schema["required"] == ["reason"]
    assert help_schema["additionalProperties"] is False
    assert help_schema["properties"]["notify"]["default"] is False
    assert "external/non-learning" in ctx.tools["learnbuddy_parent_help_request"]["schema"]["description"]

    assert ctx.tools["learnbuddy_child_submit_answer"]["toolset"] == "learnbuddy_child"
    assert ctx.tools["learnbuddy_child_status"]["toolset"] == "learnbuddy_child"
    child_help_schema = ctx.tools["learnbuddy_child_request_parent_help"]["schema"]["parameters"]
    assert ctx.tools["learnbuddy_child_request_parent_help"]["toolset"] == "learnbuddy_child"
    assert child_help_schema["required"] == ["reason"]
    assert "notify" not in child_help_schema["properties"]


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
