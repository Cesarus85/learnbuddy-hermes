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


def test_cli_help_request_records_and_can_notify_parent(capsys, tmp_path):
    data_dir = tmp_path / "cli-help-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  id: kid-help-cli
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )

    assert main([
        "help-request",
        "--config", str(config_path),
        "--subject", "german",
        "--reason", "Robin braucht Hilfe beim Aufsatz.",
        "--urgent",
        "--notify",
    ]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "created"
    request = result["help_request"]
    assert request["child_id"] == "kid-help-cli"
    assert request["subject"] == "german"
    assert request["urgent"] is True
    assert request["notification"]["status"] == "dry_run"
    assert (data_dir / "help_requests.jsonl").exists()


def test_cli_setup_creates_public_safe_config_and_storage(capsys, tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    data_dir = tmp_path / "learnbuddy-data"

    assert main([
        "setup",
        "--config", str(config_path),
        "--data-dir", str(data_dir),
        "--child-id", "learner-1",
        "--child-name", "Robin",
        "--agent-name", "StudyFox",
        "--delivery-mode", "dry_run",
        "--format", "json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "created"
    assert result["config_path"] == str(config_path)
    assert result["storage_dir"] == str(data_dir)
    assert data_dir.exists()
    text = config_path.read_text(encoding="utf-8")
    assert "id: learner-1" in text
    assert "display_name: Robin" in text
    assert "name: StudyFox" in text
    assert "mode: dry_run" in text
    assert "TOKEN" not in text
    assert "CHAT" not in text


def test_cli_setup_refuses_to_overwrite_config_without_force(capsys, tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text("child:\n  id: existing\n", encoding="utf-8")

    assert main(["setup", "--config", str(config_path)]) == 1
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "exists"
    assert "use --force" in result["error"]
    assert "existing" in config_path.read_text(encoding="utf-8")


def test_cli_backup_and_restore_round_trip_runtime_data(capsys, tmp_path):
    data_dir = tmp_path / "learnbuddy-data"
    archive_path = tmp_path / "learnbuddy-backup.zip"
    restore_dir = tmp_path / "restored-data"

    assert main(["queue", "--data-dir", str(data_dir), "--subject", "math", "--prompt", "3 + 4?", "--answer", "7"]) == 0
    queued = json.loads(capsys.readouterr().out)
    assert main(["next", "--data-dir", str(data_dir), "--exercise-id", queued["exercise"]["id"]]) == 0
    capsys.readouterr()
    assert main(["answer", "--data-dir", str(data_dir), "7"]) == 0
    capsys.readouterr()
    assert main(["help-request", "--data-dir", str(data_dir), "--reason", "Need a hint."]) == 0
    capsys.readouterr()

    assert main(["backup", "--data-dir", str(data_dir), "--output", str(archive_path)]) == 0
    backup = json.loads(capsys.readouterr().out)
    assert backup["status"] == "created"
    assert backup["archive_path"] == str(archive_path)
    assert archive_path.exists()
    assert set(backup["files"]) >= {"answers.jsonl", "exercises.jsonl", "sessions.jsonl", "state.json", "help_requests.jsonl"}

    assert main(["restore", "--archive", str(archive_path), "--data-dir", str(restore_dir)]) == 0
    restore = json.loads(capsys.readouterr().out)
    assert restore["status"] == "restored"
    assert restore["data_dir"] == str(restore_dir)
    assert sorted(restore["files"]) == sorted(backup["files"])
    assert (restore_dir / "answers.jsonl").read_text(encoding="utf-8") == (data_dir / "answers.jsonl").read_text(encoding="utf-8")


def test_cli_restore_refuses_to_overwrite_existing_data_without_force(capsys, tmp_path):
    data_dir = tmp_path / "learnbuddy-data"
    archive_path = tmp_path / "learnbuddy-backup.zip"
    restore_dir = tmp_path / "restored-data"
    restore_dir.mkdir()
    (restore_dir / "state.json").write_text('{"pending": "keep"}\n', encoding="utf-8")

    assert main(["queue", "--data-dir", str(data_dir), "--prompt", "A?", "--answer", "B"]) == 0
    capsys.readouterr()
    assert main(["backup", "--data-dir", str(data_dir), "--output", str(archive_path)]) == 0
    capsys.readouterr()

    assert main(["restore", "--archive", str(archive_path), "--data-dir", str(restore_dir)]) == 1
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "exists"
    assert "use --force" in result["error"]
    assert (restore_dir / "state.json").read_text(encoding="utf-8") == '{"pending": "keep"}\n'
