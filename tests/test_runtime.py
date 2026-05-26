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
    assert config.storage_dir.endswith("learnbuddy-data")


def test_public_example_configs_expose_child_and_agent_identity():
    repo = Path(__file__).resolve().parents[1]
    telegram = LearnBuddyConfig.from_yaml(repo / "examples" / "single-child-telegram.yaml")
    vps = LearnBuddyConfig.from_yaml(repo / "examples" / "single-child-vps-cloud-llm.yaml")

    assert telegram.child_id == "emma"
    assert telegram.child_name == "Emma"
    assert telegram.agent_name == "Lumi"
    assert telegram.max_attempts == 3
    assert vps.child_id == "emma"
    assert vps.agent_name == "Lumi"


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
