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
