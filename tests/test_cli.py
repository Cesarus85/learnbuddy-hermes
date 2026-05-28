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


def test_doctor_reports_unwritable_runtime_files(capsys, tmp_path):
    data_dir = tmp_path / "runtime-data"
    data_dir.mkdir()
    scheduled_file = data_dir / "scheduled_exercises.jsonl"
    scheduled_file.write_text("", encoding="utf-8")
    scheduled_file.chmod(0o444)
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

    try:
        assert main(["doctor", "--config", str(config_path)]) == 1
        out = capsys.readouterr().out
        assert "check=storage status=error" in out
        assert "unwritable_files=scheduled_exercises.jsonl" in out
    finally:
        scheduled_file.chmod(0o644)


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
    assert main(["status", "--config", str(config_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["pending"]["delivery"]["child"]["status"] == "dry_run"


def test_cli_deliver_pending_resends_undelivered_prompt(capsys, tmp_path):
    data_dir = tmp_path / "cli-repair-delivery-data"
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
    assert main(["queue", "--config", str(config_path), "--prompt", "100 + 101?", "--answer", "201"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    opened = json.loads(capsys.readouterr().out)
    assert opened["session"]["delivery"]["child"]["status"] == "not_attempted"

    assert main(["deliver-pending", "--config", str(config_path)]) == 0
    repaired = json.loads(capsys.readouterr().out)

    assert repaired["status"] == "sent"
    assert repaired["delivery"]["status"] == "dry_run"
    assert repaired["session"]["delivery"]["child"]["status"] == "dry_run"


def test_cli_dispatch_plan_opens_and_delivers_one_auto_exercise(capsys, tmp_path):
    data_dir = tmp_path / "cli-dispatch-data"
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
    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "5 + 6?", "--answer", "11"]) == 0
    capsys.readouterr()

    assert main(["dispatch-plan", "--config", str(config_path), "--subject", "math", "--now", "2026-05-26T10:00:00+02:00"]) == 0
    dispatched = json.loads(capsys.readouterr().out)

    assert dispatched["status"] == "opened"
    assert dispatched["delivery_status"] == "sent"
    assert dispatched["delivery"]["status"] == "dry_run"
    assert dispatched["session"]["mode"] == "auto"
    assert dispatched["session"]["requested_by"] == "system"

    assert main(["dispatch-plan", "--config", str(config_path), "--subject", "math", "--now", "2026-05-26T11:00:00+02:00"]) == 0
    skipped = json.loads(capsys.readouterr().out)
    assert skipped["status"] == "pending_exists"


def test_cli_schedule_exercise_defers_until_due_then_delivers(capsys, tmp_path):
    data_dir = tmp_path / "cli-scheduled-data"
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
    assert main([
        "schedule-exercise",
        "--config", str(config_path),
        "--subject", "math",
        "--prompt", "10 + 20?",
        "--answer", "30",
        "--due-at", "2026-05-28T10:30:00+02:00",
    ]) == 0
    scheduled = json.loads(capsys.readouterr().out)
    assert scheduled["status"] == "scheduled"
    schedule_id = scheduled["scheduled"]["id"]

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T10:29:00+02:00"]) == 0
    before_due = json.loads(capsys.readouterr().out)
    assert before_due["status"] == "no_due_scheduled_exercise"

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T10:30:00+02:00"]) == 0
    dispatched = json.loads(capsys.readouterr().out)

    assert dispatched["status"] == "opened"
    assert dispatched["scheduled"]["id"] == schedule_id
    assert dispatched["delivery_status"] == "sent"
    assert dispatched["delivery"]["status"] == "dry_run"
    assert dispatched["session"]["mode"] == "auto"
    assert dispatched["session"]["requested_by"] == "system"
    assert dispatched["session"]["source"] == "scheduled_exercise"


def test_cli_scheduled_exercise_waits_for_pending_then_bypasses_auto_limit(capsys, tmp_path):
    data_dir = tmp_path / "cli-scheduled-after-pending-data"
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
    assert main(["queue", "--config", str(config_path), "--subject", "english", "--prompt", "Was heißt Löffel auf Englisch?", "--answer", "spoon"]) == 0
    capsys.readouterr()
    assert main(["dispatch-plan", "--config", str(config_path), "--subject", "english", "--now", "2026-05-28T10:00:00+02:00"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "opened"

    assert main([
        "schedule-exercise",
        "--config", str(config_path),
        "--subject", "english",
        "--prompt", "Was heißt Auto auf Englisch?",
        "--answer", "car",
        "--due-at", "2026-05-28T10:30:00+02:00",
    ]) == 0
    scheduled = json.loads(capsys.readouterr().out)
    schedule_id = scheduled["scheduled"]["id"]

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T10:31:00+02:00"]) == 0
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["status"] == "pending_exists"

    assert main(["answer", "--config", str(config_path), "spoon"]) == 0
    capsys.readouterr()
    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T10:32:00+02:00"]) == 0
    dispatched = json.loads(capsys.readouterr().out)

    assert dispatched["status"] == "opened"
    assert dispatched["scheduled"]["id"] == schedule_id
    assert dispatched["session"]["source"] == "scheduled_exercise"
    assert dispatched["delivery_status"] == "sent"
    assert dispatched["delivery"]["status"] == "dry_run"


def test_cli_dispatch_plan_respects_allowed_hours(capsys, tmp_path):
    data_dir = tmp_path / "cli-dispatch-hours-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  allowed_hours:
    from: "07:00"
    to: "21:00"
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    assert main(["queue", "--config", str(config_path), "--prompt", "A?", "--answer", "B"]) == 0
    capsys.readouterr()

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-26T22:00:00+02:00"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "outside_allowed_hours"


def test_cli_dispatch_plan_respects_daily_auto_limit_after_completed_session(capsys, tmp_path):
    data_dir = tmp_path / "cli-dispatch-limit-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
safety:
  daily_auto_limit: 1
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    assert main(["queue", "--config", str(config_path), "--prompt", "1 + 1?", "--answer", "2"]) == 0
    first_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["queue", "--config", str(config_path), "--prompt", "2 + 2?", "--answer", "4"]) == 0
    capsys.readouterr()

    assert main(["dispatch-plan", "--config", str(config_path), "--exercise-id", first_id, "--now", "2026-05-26T10:00:00+02:00"]) == 0
    capsys.readouterr()
    assert main(["answer", "--config", str(config_path), "2"]) == 0
    capsys.readouterr()

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-26T12:00:00+02:00"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "daily_limit_reached"


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


def test_cli_daily_status_loads_env_file_for_systemd_timer(capsys, monkeypatch, tmp_path):
    data_dir = tmp_path / "cli-daily-env-data"
    config_path = tmp_path / "learnbuddy.yaml"
    env_path = tmp_path / "learnbuddy.env"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: telegram
  telegram:
    child_bot_env: CHILD_BOT_TOKEN_ENV
    allowed_child_chat_id_env: CHILD_CHAT_ID_ENV
    parent_bot_env: PARENT_BOT_TOKEN_ENV
    parent_chat_id_env: PARENT_CHAT_ID_ENV
""".strip(),
        encoding="utf-8",
    )
    env_path.write_text("PARENT_BOT_TOKEN_ENV=fake-token\nPARENT_CHAT_ID_ENV=fake-chat\n", encoding="utf-8")
    calls = []

    def fake_transport(url, payload):
        calls.append((url, payload))
        return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setenv("LEARNBUDDY_ENV_FILE", str(env_path))
    monkeypatch.delenv("PARENT_BOT_TOKEN_ENV", raising=False)
    monkeypatch.delenv("PARENT_CHAT_ID_ENV", raising=False)
    monkeypatch.setattr("learnbuddy_core.delivery._telegram_transport", fake_transport)

    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "8 + 1?", "--answer", "9"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    capsys.readouterr()
    assert main(["answer", "--config", str(config_path), "9"]) == 0
    capsys.readouterr()

    assert main(["daily-status", "--config", str(config_path), "--notify"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "sent"
    assert result["notification"]["status"] == "sent"
    assert result["notification"]["message_id"] == "42"
    assert calls and "fake-token" in calls[0][0]
    assert calls[0][1]["chat_id"] == "fake-chat"


def test_cli_daily_status_notifies_once_per_day_and_skips_duplicate(capsys, tmp_path):
    data_dir = tmp_path / "cli-daily-status-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "8 + 1?", "--answer", "9"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    capsys.readouterr()
    assert main(["answer", "--config", str(config_path), "9"]) == 0
    capsys.readouterr()

    assert main(["daily-status", "--config", str(config_path), "--notify"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "sent"
    assert first["report"]["answers"] == 1
    assert first["notification"]["status"] == "dry_run"
    assert "Tagesstatus" in first["report"]["text"]

    assert main(["daily-status", "--config", str(config_path), "--notify"]) == 0
    duplicate = json.loads(capsys.readouterr().out)
    assert duplicate["status"] == "already_sent"
    assert duplicate["notification"] is None


def test_cli_daily_status_respects_pause_today_and_resume(capsys, tmp_path):
    data_dir = tmp_path / "cli-daily-pause-data"
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

    assert main(["automation", "--config", str(config_path), "pause-today", "--reason", "Familientag", "--now", "2026-05-27T10:00:00+02:00"]) == 0
    paused = json.loads(capsys.readouterr().out)
    assert paused["status"] == "paused"
    assert paused["pause_date"] == "2026-05-27"

    assert main(["daily-status", "--config", str(config_path), "--notify", "--include-empty", "--now", "2026-05-27T21:00:00+02:00"]) == 0
    skipped = json.loads(capsys.readouterr().out)
    assert skipped["status"] == "automation_paused"
    assert skipped["notification"] is None

    assert main(["automation", "--config", str(config_path), "resume", "--now", "2026-05-27T21:05:00+02:00"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["status"] == "active"

    assert main(["daily-status", "--config", str(config_path), "--notify", "--include-empty", "--now", "2026-05-27T21:10:00+02:00"]) == 0
    sent = json.loads(capsys.readouterr().out)
    assert sent["status"] == "sent"
    assert sent["notification"]["status"] == "dry_run"


def test_cli_daily_status_skips_empty_report_unless_included(capsys, tmp_path):
    data_dir = tmp_path / "cli-daily-empty-data"
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

    assert main(["daily-status", "--config", str(config_path), "--notify", "--now", "2026-05-27T21:00:00+02:00"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "no_activity"
    assert result["notification"] is None
    assert result["report"]["answers"] == 0


def test_cli_daily_status_sends_started_unanswered_day_without_include_empty(capsys, tmp_path):
    data_dir = tmp_path / "cli-daily-started-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "8 + 1?", "--answer", "9"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    capsys.readouterr()

    assert main(["daily-status", "--config", str(config_path), "--notify"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "sent"
    assert result["report"]["answers"] == 0
    assert result["report"]["sessions_started"] == 1
    assert result["notification"]["status"] == "dry_run"
    assert "Antworten: noch keine abgegeben" in result["report"]["text"]


def test_cli_weekly_status_summarizes_recommendations_and_skips_duplicate(capsys, tmp_path):
    data_dir = tmp_path / "cli-weekly-status-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
storage:
  data_dir: {data_dir}
child:
  display_name: Robin
agent:
  name: StudyFox
delivery:
  mode: dry_run
""".strip(),
        encoding="utf-8",
    )
    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "8 + 1?", "--answer", "9"]) == 0
    exercise_id = json.loads(capsys.readouterr().out)["exercise"]["id"]
    assert main(["next", "--config", str(config_path), "--exercise-id", exercise_id]) == 0
    capsys.readouterr()
    assert main(["answer", "--config", str(config_path), "3"]) == 0
    capsys.readouterr()

    assert main(["weekly-status", "--config", str(config_path), "--notify", "--now", "2026-05-31T19:00:00+02:00"]) == 0
    first = json.loads(capsys.readouterr().out)

    assert first["status"] == "sent"
    assert first["report"]["week_key"] == "2026-05-25/2026-05-31"
    assert first["report"]["answers"] == 1
    assert first["report"]["correct"] == 0
    assert first["notification"]["status"] == "dry_run"
    assert "Wochenbericht" in first["report"]["text"]
    assert "Empfehlungen" in first["report"]["text"]
    assert first["report"]["recommendations"]

    assert main(["weekly-status", "--config", str(config_path), "--notify", "--now", "2026-05-31T20:00:00+02:00"]) == 0
    duplicate = json.loads(capsys.readouterr().out)
    assert duplicate["status"] == "already_sent"
    assert duplicate["notification"] is None


def test_cli_weekly_status_respects_pause_today(capsys, tmp_path):
    data_dir = tmp_path / "cli-weekly-pause-data"
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

    assert main(["automation", "--config", str(config_path), "pause-today", "--now", "2026-05-31T10:00:00+02:00"]) == 0
    capsys.readouterr()
    assert main(["weekly-status", "--config", str(config_path), "--notify", "--include-empty", "--now", "2026-05-31T19:00:00+02:00"]) == 0
    skipped = json.loads(capsys.readouterr().out)

    assert skipped["status"] == "automation_paused"
    assert skipped["notification"] is None


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
    assert main([
        "schedule-exercise",
        "--data-dir", str(data_dir),
        "--subject", "math",
        "--prompt", "8 + 9?",
        "--answer", "17",
        "--due-at", "2026-05-28T10:30:00+02:00",
    ]) == 0
    capsys.readouterr()
    assert main([
        "plan", "create",
        "--data-dir", str(data_dir),
        "--title", "Mathe Woche",
        "--subject", "math",
        "--daily-goal", "1",
    ]) == 0
    capsys.readouterr()

    assert main(["backup", "--data-dir", str(data_dir), "--output", str(archive_path)]) == 0
    backup = json.loads(capsys.readouterr().out)
    assert backup["status"] == "created"
    assert backup["archive_path"] == str(archive_path)
    assert archive_path.exists()
    assert set(backup["files"]) >= {
        "answers.jsonl",
        "exercises.jsonl",
        "sessions.jsonl",
        "state.json",
        "help_requests.jsonl",
        "scheduled_exercises.jsonl",
        "plans.jsonl",
        "plan-state.json",
    }

    assert main(["restore", "--archive", str(archive_path), "--data-dir", str(restore_dir)]) == 0
    restore = json.loads(capsys.readouterr().out)
    assert restore["status"] == "restored"
    assert restore["data_dir"] == str(restore_dir)
    assert sorted(restore["files"]) == sorted(backup["files"])
    assert (restore_dir / "answers.jsonl").read_text(encoding="utf-8") == (data_dir / "answers.jsonl").read_text(encoding="utf-8")
    assert (restore_dir / "scheduled_exercises.jsonl").read_text(encoding="utf-8") == (data_dir / "scheduled_exercises.jsonl").read_text(encoding="utf-8")
    assert (restore_dir / "plans.jsonl").read_text(encoding="utf-8") == (data_dir / "plans.jsonl").read_text(encoding="utf-8")
    assert (restore_dir / "plan-state.json").read_text(encoding="utf-8") == (data_dir / "plan-state.json").read_text(encoding="utf-8")


def test_cli_learning_plan_create_status_control_and_dispatch(capsys, tmp_path):
    data_dir = tmp_path / "learnbuddy-data"
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
    assert main(["queue", "--config", str(config_path), "--subject", "math", "--prompt", "1 + 1?", "--answer", "2"]) == 0
    math = json.loads(capsys.readouterr().out)["exercise"]
    assert main(["queue", "--config", str(config_path), "--subject", "english", "--prompt", "Translate: Hund", "--answer", "dog"]) == 0
    english = json.loads(capsys.readouterr().out)["exercise"]

    assert main([
        "plan",
        "create",
        "--config", str(config_path),
        "--title", "Englisch Woche",
        "--subject", "english",
        "--focus", "Wortschatz",
        "--daily-goal", "1",
    ]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "active"
    assert created["plan"]["title"] == "Englisch Woche"
    assert created["plan"]["subjects"] == ["english"]

    assert main(["plan", "status", "--config", str(config_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["active_plan"]["id"] == created["plan"]["id"]

    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T10:00:00+02:00"]) == 0
    dispatched = json.loads(capsys.readouterr().out)
    assert dispatched["status"] == "opened"
    assert dispatched["plan"]["id"] == created["plan"]["id"]
    assert dispatched["exercise"]["id"] == english["id"]
    assert dispatched["exercise"]["id"] != math["id"]
    assert dispatched["session"]["source"] == "learning_plan"
    assert dispatched["session"]["plan_id"] == created["plan"]["id"]
    assert dispatched["delivery_status"] == "sent"
    assert dispatched["delivery"]["status"] == "dry_run"

    assert main(["answer", "--config", str(config_path), "dog"]) == 0
    capsys.readouterr()
    assert main(["dispatch-plan", "--config", str(config_path), "--now", "2026-05-28T11:00:00+02:00"]) == 0
    limit = json.loads(capsys.readouterr().out)
    assert limit["status"] == "plan_daily_goal_reached"

    assert main(["plan", "pause", "--config", str(config_path), "--reason", "Familientag"]) == 0
    paused = json.loads(capsys.readouterr().out)
    assert paused["status"] == "paused"
    assert paused["reason"] == "Familientag"
    assert main(["plan", "resume", "--config", str(config_path)]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["status"] == "active"


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
