from pathlib import Path

from learnbuddy_core.config import default_storage_dir
from learnbuddy_core.runtime import LearnBuddyRuntime


def test_default_storage_dir_uses_isolated_hermes_home(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("LEARNBUDDY_STORAGE_DIR", raising=False)

    assert default_storage_dir() == hermes_home / "family" / "learnbuddy"


def test_runtime_opens_exercise_queues_second_and_promotes_after_exhaustion(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3)
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
    assert runtime.status()["pending"]["exercise_id"] == second["id"]
    assert runtime.status()["queue"] == []

    correct = runtime.submit_answer("A dog")
    assert correct["result"] == "correct"
    assert correct["correct"] is True
    assert runtime.status()["pending"] is None


def test_runtime_parent_report_uses_synthetic_sessions_and_answers(tmp_path):
    runtime = LearnBuddyRuntime(tmp_path / "learnbuddy", max_attempts=3)
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
    assert "1/4 richtig" in report["text"]
