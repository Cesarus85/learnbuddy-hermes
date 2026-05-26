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


def test_telegram_answer_watcher_delivers_promoted_queued_exercise_after_correct_answer(tmp_path, monkeypatch):
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
    first = runtime.add_exercise({"subject": "math", "prompt": "2 + 2?", "answer": "4"})
    second = runtime.add_exercise({"subject": "german", "prompt": "Artikel von Haus?", "answer": "das"})
    opened = runtime.open_exercise(first["id"])
    queued = runtime.open_exercise(second["id"])
    assert queued["status"] == "queued"
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 30, "message": {"message_id": 1, "date": pending_ts + 1, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "4"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "processed"
    assert result["result"] == "correct"
    assert runtime.status()["pending"]["exercise_id"] == second["id"]
    assert runtime.status()["queue"] == []
    assert result["promoted_session"]["exercise_id"] == second["id"]
    assert result["next_child_delivery"]["status"] == "dry_run"


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


def test_telegram_answer_watcher_resends_undelivered_pending_prompt_when_no_answer(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    config = LearnBuddyConfig(
        storage_dir=str(data_dir),
        delivery_mode="dry_run",
        child_telegram_bot_token_env="CHILD_BOT",
        child_telegram_chat_id_env="CHILD_CHAT",
    )
    monkeypatch.setenv("CHILD_BOT", "child-secret-token")
    monkeypatch.setenv("CHILD_CHAT", "123")
    runtime = LearnBuddyRuntime(data_dir)
    exercise = runtime.add_exercise({"prompt": "100 + 101?", "answer": "201"})
    runtime.open_exercise(exercise["id"])

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": []}
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "no_answer"
    assert result["pending_delivery"]["status"] == "dry_run"
    assert runtime.status()["pending"]["delivery"]["child"]["status"] == "dry_run"



def test_telegram_answer_watcher_resends_pending_prompt_for_child_nochmal(tmp_path, monkeypatch):
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
    exercise = runtime.add_exercise({"subject": "math", "prompt": "100 + 101?", "answer": "201"})
    opened = runtime.open_exercise(exercise["id"])
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 40, "message": {"message_id": 7, "date": pending_ts + 1, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "Nochmal bitte"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "child_command"
    assert result["command"] == "repeat"
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["child_delivery"]["metadata"]["kind"] == "pending_exercise_repeat"
    assert runtime.status()["pending"]["exercise_id"] == exercise["id"]
    assert runtime.status()["pending"]["attempts"] == 0
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 41



def test_telegram_answer_watcher_turns_child_help_into_parent_help_request(tmp_path, monkeypatch):
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
    exercise = runtime.add_exercise({"subject": "german", "prompt": "Artikel von Haus?", "answer": "das"})
    opened = runtime.open_exercise(exercise["id"])
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 50, "message": {"message_id": 8, "date": pending_ts + 1, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "Ich weiß nicht"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "child_command"
    assert result["command"] == "help"
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["child_delivery"]["metadata"]["kind"] == "child_help_ack"
    assert result["parent_delivery"]["status"] == "dry_run"
    assert result["help_request"]["subject"] == "german"
    assert result["help_request"]["requested_by"] == "child"
    assert "Ich weiß nicht" in result["help_request"]["reason"]
    assert runtime.status()["pending"]["exercise_id"] == exercise["id"]
    assert runtime.status()["pending"]["attempts"] == 0
    assert len(runtime.help_requests()) == 1
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 51



def test_telegram_answer_watcher_tells_child_to_finish_pending_before_noch_eine(tmp_path, monkeypatch):
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
    exercise = runtime.add_exercise({"subject": "math", "prompt": "100 + 101?", "answer": "201"})
    opened = runtime.open_exercise(exercise["id"])
    pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).timestamp())

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 60, "message": {"message_id": 9, "date": pending_ts + 1, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "Noch eine"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(config, state_file=tmp_path / "watch.json", transport=fake_transport)

    assert result["status"] == "child_command"
    assert result["command"] == "next"
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["child_delivery"]["metadata"]["kind"] == "finish_pending_first"
    assert "Erst diese Aufgabe" in result["child_delivery"]["text"]
    assert runtime.status()["pending"]["exercise_id"] == exercise["id"]
    assert runtime.status()["pending"]["attempts"] == 0
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 61



def test_telegram_answer_watcher_dispatches_policy_bounded_noch_eine_without_pending(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    config = LearnBuddyConfig(
        child_id="learner-1",
        child_name="Learner",
        agent_name="LearnBuddy",
        storage_dir=str(data_dir),
        delivery_mode="dry_run",
        child_telegram_bot_token_env="CHILD_BOT",
        child_telegram_chat_id_env="CHILD_CHAT",
    )
    monkeypatch.setenv("CHILD_BOT", "child-secret-token")
    monkeypatch.setenv("CHILD_CHAT", "123")
    runtime = LearnBuddyRuntime(data_dir, child_id="learner-1", child_name="Learner", agent_name="LearnBuddy")
    exercise = runtime.add_exercise({"subject": "math", "prompt": "5 + 6?", "answer": "11"})

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 70, "message": {"message_id": 10, "date": 1_779_790_800, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "Noch eine bitte"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(
        config,
        state_file=tmp_path / "watch.json",
        transport=fake_transport,
        now="2026-05-26T10:00:00+02:00",
    )

    assert result["status"] == "child_command"
    assert result["command"] == "next"
    assert result["dispatch"]["status"] == "opened"
    assert result["dispatch"]["session"]["exercise_id"] == exercise["id"]
    assert result["dispatch"]["session"]["mode"] == "auto"
    assert result["dispatch"]["session"]["requested_by"] == "system"
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["child_delivery"]["metadata"]["kind"] == "child_requested_next_exercise"
    assert runtime.status()["pending"]["exercise_id"] == exercise["id"]
    assert runtime.status()["pending"]["delivery"]["child"]["status"] == "dry_run"
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 71



def test_telegram_answer_watcher_rejects_noch_eine_when_daily_limit_is_reached(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    config = LearnBuddyConfig(
        child_id="learner-1",
        child_name="Learner",
        agent_name="LearnBuddy",
        storage_dir=str(data_dir),
        daily_auto_limit=1,
        delivery_mode="dry_run",
        child_telegram_bot_token_env="CHILD_BOT",
        child_telegram_chat_id_env="CHILD_CHAT",
    )
    monkeypatch.setenv("CHILD_BOT", "child-secret-token")
    monkeypatch.setenv("CHILD_CHAT", "123")
    runtime = LearnBuddyRuntime(data_dir, child_id="learner-1", child_name="Learner", agent_name="LearnBuddy")
    first = runtime.add_exercise({"subject": "math", "prompt": "2 + 2?", "answer": "4"})
    runtime.open_exercise(first["id"], mode="auto", requested_by="system", timestamp="2026-05-26T07:30:00+00:00")
    assert runtime.submit_answer("4")["result"] == "correct"
    runtime.add_exercise({"subject": "german", "prompt": "Artikel von Baum?", "answer": "der"})

    def fake_transport(url, payload):
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {"update_id": 80, "message": {"message_id": 11, "date": 1_779_790_800, "chat": {"id": 123}, "from": {"is_bot": False}, "text": "noch eine"}},
                ],
            }
        raise AssertionError(url)

    result = process_child_telegram_answers(
        config,
        state_file=tmp_path / "watch.json",
        transport=fake_transport,
        now="2026-05-26T10:00:00+02:00",
    )

    assert result["status"] == "child_command"
    assert result["command"] == "next"
    assert result["dispatch"]["status"] == "daily_limit_reached"
    assert result["child_delivery"]["status"] == "dry_run"
    assert result["child_delivery"]["metadata"]["kind"] == "child_next_rejected"
    assert "Für heute reicht" in result["child_delivery"]["text"]
    assert runtime.status()["pending"] is None
    assert json.loads((tmp_path / "watch.json").read_text())["offset"] == 81



def test_telegram_answer_watcher_reports_missing_env(tmp_path, monkeypatch):
    config = LearnBuddyConfig(storage_dir=str(tmp_path / "runtime"), child_telegram_bot_token_env="MISSING_BOT", child_telegram_chat_id_env="MISSING_CHAT")
    monkeypatch.delenv("MISSING_BOT", raising=False)
    monkeypatch.delenv("MISSING_CHAT", raising=False)

    result = process_child_telegram_answers(config)

    assert result == {"status": "not_configured", "missing": ["MISSING_BOT", "MISSING_CHAT"]}
