from learnbuddy_core.cli import main


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "LearnBuddy doctor" in out
