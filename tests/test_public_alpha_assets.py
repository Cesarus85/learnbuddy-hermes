from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_MARKERS = {
    "PRIVATE_CHILD_REFERENCE",
    "PRIVATE_PARENT_REFERENCE",
    "PRIVATE_AGENT_REFERENCE",
    "PRIVATE_HOST_REFERENCE",
}
SECRET_MARKERS = {"TOKEN", "CHAT_ID", "PASSWORD", "SECRET", "API_KEY"}


def read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def assert_public_safe_text(text: str) -> None:
    for marker in PRIVATE_MARKERS:
        assert marker not in text
    for marker in SECRET_MARKERS:
        assert f"{marker}=" not in text
        assert f"{marker}:" not in text


def test_demo_artifacts_are_ignored_by_default() -> None:
    gitignore = read_repo_file(".gitignore")
    expected_patterns = [
        "learnbuddy.yaml",
        "data/",
        "restored-learnbuddy-data/",
        "learnbuddy-backup*.zip",
    ]
    for pattern in expected_patterns:
        assert pattern in gitignore


def test_public_alpha_docs_are_not_stub_placeholders() -> None:
    required_docs = [
        "README.md",
        "SECURITY.md",
        "PRIVACY.md",
        "docs/quickstart-telegram.md",
        "docs/setup-child-profile.md",
        "docs/quickstart-vps.md",
        "docs/demo-flow.md",
        "INSTALL.md",
    ]
    forbidden_phrases = [
        "early scaffold",
        "not ready yet",
        "Status: planned",
        "Until the setup wizard lands",
    ]

    for relative_path in required_docs:
        text = read_repo_file(relative_path)
        assert_public_safe_text(text)
        for phrase in forbidden_phrases:
            assert phrase not in text


def test_public_docs_include_telegram_parent_command_contracts() -> None:
    text = read_repo_file("docs/telegram-command-contracts.md")
    required_snippets = [
        "Parent Telegram command contracts",
        "learnbuddy_learning_status",
        "learnbuddy_parent_report",
        "learnbuddy_deliver_pending_exercise",
        "learnbuddy_dispatch_plan",
        "learnbuddy_create_and_send_exercise",
        "Web/PWA",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_telegram_quickstart_documents_child_control_messages() -> None:
    text = read_repo_file("docs/quickstart-telegram.md")
    required_snippets = [
        "Child control messages",
        "Nochmal",
        "Ich weiß nicht",
        "parent-help request",
        "without incrementing attempts",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_telegram_e2e_smoke_runbook_documents_controlled_flow() -> None:
    text = read_repo_file("docs/telegram-e2e-smoke.md")
    required_snippets = [
        "# Telegram E2E Smoke Runbook",
        "controlled staging smoke",
        "Parent creates and sends one exercise",
        "Child requests help",
        "Parent receives a bounded help request",
        "Child answers correctly",
        "deliver-pending repairs missing delivery metadata",
        "No live child or parent Telegram message is required",
        "e2e_smoke=ok",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_demo_exercise_fixture_is_valid_and_public_safe() -> None:
    fixture = ROOT / "examples" / "exercises" / "de" / "grade-5-mixed.jsonl"
    lines = [line for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) >= 6
    subjects = set()
    exercise_ids = set()
    for line in lines:
        assert_public_safe_text(line)
        item = json.loads(line)
        assert set(item) >= {
            "id",
            "subject",
            "type",
            "prompt",
            "expected_answers",
            "difficulty",
            "hint",
            "success",
        }
        assert item["id"] not in exercise_ids
        exercise_ids.add(item["id"])
        subjects.add(item["subject"])
        assert isinstance(item["expected_answers"], list)
        assert item["expected_answers"]
        assert 1 <= item["difficulty"] <= 5

    assert {"math", "german", "english"} <= subjects


def test_install_guide_covers_hermes_and_learnbuddy_setup() -> None:
    text = read_repo_file("INSTALL.md")
    required_snippets = [
        "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash",
        "hermes setup",
        "git clone https://github.com/Cesarus85/learnbuddy-hermes.git",
        "python -m pip install -e '.[test]'",
        "learnbuddy setup",
        "learnbuddy doctor",
        "learnbuddy dispatch-plan",
        "learnbuddy next --deliver",
        "learnbuddy deliver-pending",
        "learnbuddy report --notify",
        "delivery.mode: dry_run",
        "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN",
        "hermes plugins",
        "learnbuddy_child",
        "scripts/setup-child-profile.sh",
        "pytest -q",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_demo_flow_documents_full_public_smoke_path() -> None:
    text = read_repo_file("docs/demo-flow.md")
    required_snippets = [
        "learnbuddy setup",
        "learnbuddy doctor",
        "learnbuddy queue",
        "learnbuddy dispatch-plan",
        "learnbuddy next --deliver",
        "learnbuddy deliver-pending",
        "learnbuddy answer",
        "learnbuddy report --notify",
        "learnbuddy backup",
        "learnbuddy restore",
        "delivery.mode: dry_run",
        "examples/exercises/de/grade-5-mixed.jsonl",
    ]
    for snippet in required_snippets:
        assert snippet in text
