import json

from learnbuddy_core.cli import main


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "LearnBuddy doctor" in out
    assert "overall=ok" in out


def test_doctor_displays_configured_child_and_agent(capsys, tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
child:
  id: kid-3
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    assert main(["doctor", "--config", str(config_path)]) == 0
    out = capsys.readouterr().out

    assert "child_id=kid-3" in out
    assert "child_name=Robin" in out
    assert "agent_name=StudyFox" in out
    assert "check=config status=ok" in out
    assert "check=delivery status=ok mode=dry_run" in out


def test_doctor_reports_missing_telegram_env_without_leaking_values(capsys, tmp_path, monkeypatch):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
delivery:
  mode: telegram
  child:
    type: telegram
    bot_token_env: CHILD_TOKEN_ENV
    allowed_chat_ids_env: CHILD_CHAT_ENV
  parents:
    - type: telegram
      bot_token_env: PARENT_TOKEN_ENV
      target_env: PARENT_CHAT_ENV
""".strip(),
        encoding="utf-8",
    )
    for name in ["CHILD_TOKEN_ENV", "CHILD_CHAT_ENV", "PARENT_TOKEN_ENV", "PARENT_CHAT_ENV"]:
        monkeypatch.delenv(name, raising=False)

    assert main(["doctor", "--config", str(config_path)]) == 1
    out = capsys.readouterr().out

    assert "overall=error" in out
    assert "check=delivery_child status=error missing=CHILD_TOKEN_ENV,CHILD_CHAT_ENV" in out
    assert "check=delivery_parent status=error missing=PARENT_TOKEN_ENV,PARENT_CHAT_ENV" in out


def test_doctor_json_output_is_machine_readable(capsys, tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
child:
  id: kid-json
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    assert main(["doctor", "--config", str(config_path), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["overall"] == "ok"
    assert report["config"]["child_id"] == "kid-json"
    assert {check["name"] for check in report["checks"]} >= {"config", "storage", "delivery"}


def test_doctor_accepts_creatable_storage_path(capsys, tmp_path, monkeypatch):
    hermes_home = tmp_path / "fresh-hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out

    assert "overall=ok" in out
    assert f"storage_dir={hermes_home / 'family' / 'learnbuddy'}" in out
    assert "creatable=True" in out


def test_cli_exercise_lifecycle_uses_configured_storage(capsys, tmp_path):
    data_dir = tmp_path / "cli-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  id: kid-cli
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "2 + 2?", "--answer", "4"]) == 0
    queued = json.loads(capsys.readouterr().out)
    assert queued["status"] == "created"
    exercise_id = queued["exercise"]["id"]

    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    opened = json.loads(capsys.readouterr().out)
    assert opened["status"] == "opened"
    assert opened["session"]["child_id"] == "kid-cli"
    assert opened["prompt"] == "2 + 2?"

    assert main(["answer", "--config", str(config_path), "4"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["result"] == "correct"

    assert main(["status", "--config", str(config_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["pending"] is None

    assert main(["report", "--config", str(config_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["child_id"] == "kid-cli"
    assert report["correct"] == 1


def test_cli_next_exercise_can_dry_run_deliver(capsys, tmp_path):
    data_dir = tmp_path / "cli-delivery-data"
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
    assert main(["queue", "--config", str(config_path), "--prompt", "Translate: cat", "--answer", "Katze"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]

    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id, "--deliver"]) == 0
    opened = json.loads(capsys.readouterr().out)

    assert opened["delivery"] == {
        "status": "dry_run",
        "adapter": "dry_run",
        "target": "child",
        "message_id": None,
        "error": None,
    }


def test_cli_report_can_dry_run_notify_parent(capsys, tmp_path):
    data_dir = tmp_path / "cli-notify-data"
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
    assert main(["report", "--config", str(config_path), "--notify"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["notification"]["status"] == "dry_run"
    assert report["notification"]["target"] == "parent"
