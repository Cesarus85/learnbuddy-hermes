from datetime import datetime, timezone
import json

from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.runtime import LearnBuddyRuntime
from learnbuddy_core.telegram_answer_watcher import process_child_telegram_answers


def test_telegram_answer_watcher_processes_child_answer_and_notifies(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    config = LearnBuddyConfig(
        child_id="learner-1",
        child_name="Learner",
        agent_name="LearnBuddy",
        storage_dir=str(data_dir),
        delivery_mode="dry_run",
        child_telegram_bot_token_env="CHILD_BOT",
        child_telegram_chat_id_env="CHILD_CHAT",
        parent_telegram_bot_token_env="PARENT_BOT",
        parent_telegram_chat_id_env="PARENT_CHAT",
    )
    monkeypatch.setenv("CHILD_BOT", "child-secret-token")
    monkeypatch.setenv("CHILD_CHAT", "123")
    monkeypatch.setenv("PARENT_BOT", "parent-secret-token")
    monkeypatch.setenv("PARENT_CHAT", "456")
    runtime = LearnBuddyRuntime(data_dir, child_id="learner-1", child_name="Learner", agent_name="LearnBuddy")
    exercise = runtime.add_exercise({"subject": "math", "prompt": "Stimmt das? 3 + 3 = 6?", "answer": "Ja"})
    opened = runtime.open_exercise(exercise["id"])
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())
    calls = []

    def fake_transport(url, payload):
        calls.append((url, payload))
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 10, "message": {"message_id": 1, "date": pending_ts - 10, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "old"}},
                    {"update_id": 11, "message": {"message_id": 2, "date": pending_ts + 5, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "Ja"}},
                ],
            }
        if url.endswith("/sendMessage"):
            return {"ok": True, "result": {"message_id": 99}}
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "processed"
    assert result["result"] == "correct"
    assert result["correct"] is True
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["parent_delivery"]["status"] == "dry_run"
    assert runtime.status()["pending"] is None
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 12


def test_telegram_answer_watcher_ignores_commands_and_old_messages(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    config = LearnBuddyConfig(storage_dir=str(data_dir), child_telegram_bot_token_env="CHILD_BOT", child_telegram_chat_id_env="CHILD_CHAT")
    monkeypatch.setenv("CHILD_BOT", "child-secret-token")
    monkeypatch.setenv("CHILD_CHAT", "123")
    runtime = LearnBuddyRuntime(data_dir)
    exercise = runtime.add_exercise({"prompt": "2 + 2?", "answer": "4"})
    opened = runtime.open_exercise(exercise["id"])
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())

    def fake_transport(url, payload):
        return {
            "ok": True,
            "result": [
                {"update_id": 20, "message": {"message_id": 1, "date": pending_ts - 10, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "4"}},
                {"update_id": 21, "message": {"message_id": 2, "date": pending_ts + 1, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "/start"}},
            ],
        }

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "no_answer"
    assert runtime.status()["pending"]["exercise_id"] == exercise["id"]
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 22


def test_telegram_answer_watcher_reports_missing_env(tmp_path, monkeypatch):
    config = LearnBuddyConfig(storage_dir=str(tmp_path / "runtime"), child_telegram_bot_token_env="MISSING_BOT", child_telegram_chat_id_env="MISSING_CHAT")
    monkeypatch.delenv("MISSING_BOT", raising=False)
    monkeypatch.delenv("MISSING_CHAT", raising=False)

    result = process_child_telegram_answers(config)

    assert result == {"status": "not_configured", "missing": ["MISSING_BOT", "MISSING_CHAT"]}
