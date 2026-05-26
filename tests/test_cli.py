from learnbuddy_core.cli import main


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "LearnBuddy doctor" in out


def test_doctor_displays_configured_child_and_agent(capsys, tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
child:
  id: kid-3
  display_name: Robin
agent:
  name: StudyFox
""".strip(),
        encoding="utf-8",
    )

    assert main(["doctor", "--config", str(config_path)]) == 0
    out = capsys.readouterr().out

    assert "child_id=kid-3" in out
    assert "child_name=Robin" in out
    assert "agent_name=StudyFox" in out
