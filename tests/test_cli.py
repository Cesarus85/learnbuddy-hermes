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
