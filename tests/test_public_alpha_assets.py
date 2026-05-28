from __future__ import annotations

import json
import os
import subprocess
import sys
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


def test_public_release_versions_are_consistent() -> None:
    pyproject = read_repo_file("pyproject.toml")
    package_init = read_repo_file("src/learnbuddy_core/__init__.py")
    plugin_yaml = read_repo_file("plugins/learnbuddy-learning/plugin.yaml")
    plugin_init = read_repo_file("plugins/learnbuddy-learning/__init__.py")
    readme = read_repo_file("README.md")
    install = read_repo_file("INSTALL.md")

    assert 'version = "0.1.2a0"' in pyproject
    assert '__version__ = "0.1.2a0"' in package_init
    assert "version: 0.1.2-alpha" in plugin_yaml
    assert 'PLUGIN_VERSION = "0.1.2-alpha"' in plugin_init
    assert "0.1.2-alpha" in readme
    assert "git checkout v0.1.2-alpha" in install


def test_public_alpha_docs_are_not_stub_placeholders() -> None:
    required_docs = [
        "README.md",
        "SECURITY.md",
        "PRIVACY.md",
        "docs/quickstart-telegram.md",
        "docs/quickstart-docker.md",
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
        "learnbuddy_daily_parent_status",
        "learnbuddy_weekly_parent_status",
        "learnbuddy_parent_automation_control",
        "heute pausieren",
        "learnbuddy_deliver_pending_exercise",
        "learnbuddy_dispatch_plan",
        "learnbuddy_schedule_exercise",
        "learnbuddy_create_learning_plan",
        "learnbuddy_learning_plan_status",
        "learnbuddy_control_learning_plan",
        "learnbuddy_add_learning_material",
        "learnbuddy_import_learning_material_file",
        "learnbuddy_material_status",
        "learnbuddy_approve_material_tasks",
        "learnbuddy material add-file",
        "LEARNBUDDY_MATERIAL_OCR_COMMAND",
        "material-sets.jsonl",
        "source=learning_plan",
        "plan_id",
        "learnbuddy_create_and_send_exercise",
        "answer_or_expected_answers",
        "Frage Learner folgende Aufgaben",
        "scripts/setup-parent-profile.sh",
        "scripts/install-daily-status-timer.sh",
        "scripts/install-weekly-status-timer.sh",
        "scripts/install-dispatch-timer.sh",
        "Web/PWA",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_parent_profile_assets_support_live_command_contract_routing() -> None:
    soul = read_repo_file("templates/parent-profile/SOUL.md")
    script = read_repo_file("scripts/setup-parent-profile.sh")
    child_script = read_repo_file("scripts/setup-child-profile.sh")
    daily_timer = read_repo_file("scripts/install-daily-status-timer.sh")
    weekly_timer = read_repo_file("scripts/install-weekly-status-timer.sh")
    dispatch_timer = read_repo_file("scripts/install-dispatch-timer.sh")
    install = read_repo_file("INSTALL.md")

    for text in (soul, script, child_script, daily_timer, weekly_timer, dispatch_timer, install):
        assert_public_safe_text(text)

    required_soul_snippets = [
        "learnbuddy_parent_command_contracts",
        "learnbuddy_learning_status",
        "learnbuddy_create_and_send_exercise",
        "learnbuddy_schedule_exercise",
        "learnbuddy_dispatch_plan",
        "learnbuddy_create_learning_plan",
        "learnbuddy_learning_plan_status",
        "learnbuddy_control_learning_plan",
        "learnbuddy_add_learning_material",
        "learnbuddy_import_learning_material_file",
        "learnbuddy_material_status",
        "learnbuddy_approve_material_tasks",
        "learnbuddy_daily_parent_status",
        "learnbuddy_weekly_parent_status",
        "learnbuddy_parent_automation_control",
        "answer_or_expected_answers",
        "Do not call",
        "learnbuddy_child",
        "Frage Learner folgende Aufgaben",
    ]
    for snippet in required_soul_snippets:
        assert snippet in soul

    required_script_snippets = [
        "templates/parent-profile/SOUL.md",
        'platform_toolsets["telegram"] = ["learnbuddy_learning"]',
        'known_plugin_toolsets["telegram"] = ["learnbuddy_learning", "learnbuddy_child"]',
        "LEARNBUDDY_CONFIG_PATH",
        "LEARNBUDDY_ENV_FILE",
        "python3",
    ]
    for snippet in required_script_snippets:
        assert snippet in script

    assert "scripts/setup-parent-profile.sh" in install
    assert "learnbuddy_parent_command_contracts" in install
    required_timer_snippets = [
        "learnbuddy daily-status --notify",
        "OnCalendar",
        "Persistent=true",
        "pause-today",
        ".venv/bin/python",
        "--config",
        "python3",
    ]
    for snippet in required_timer_snippets:
        assert snippet in daily_timer
    assert "scripts/install-daily-status-timer.sh" in install
    required_weekly_timer_snippets = [
        "learnbuddy weekly-status --notify",
        "OnCalendar",
        "Persistent=true",
        ".venv/bin/python",
        "--config",
        "python3",
        "once-per-week",
        "empty-week",
    ]
    for snippet in required_weekly_timer_snippets:
        assert snippet in weekly_timer
    assert "scripts/install-weekly-status-timer.sh" in install
    required_dispatch_timer_snippets = [
        "learnbuddy dispatch-plan",
        "OnUnitActiveSec",
        "Persistent=true",
        ".venv/bin/python",
        "--config",
        "python3",
        "systemd --user timer",
        "due scheduled exercises",
    ]
    for snippet in required_dispatch_timer_snippets:
        assert snippet in dispatch_timer
    assert "scripts/install-dispatch-timer.sh" in install
    assert "learnbuddy_learning" in child_script


def test_docs_document_onboarding_doctor_hardening() -> None:
    install = read_repo_file("INSTALL.md")
    telegram = read_repo_file("docs/quickstart-telegram.md")
    child_profile = read_repo_file("docs/setup-child-profile.md")
    roadmap = read_repo_file("docs/extraction-roadmap.md")
    readme = read_repo_file("README.md")

    for text in (install, telegram, child_profile, roadmap, readme):
        assert_public_safe_text(text)

    required_snippets = [
        "learnbuddy doctor --config ./learnbuddy.yaml --parent-profile learnbuddy-parent --child-profile learnbuddy-child",
        "--child-gateway-service hermes-gateway-learnbuddy-child",
        "--dispatch-timer-profile learnbuddy-parent",
        "parent_profile",
        "child_profile",
        "child_gateway_service",
        "dispatch_timer",
        "known_plugin_toolsets",
        "LEARNBUDDY_CONFIG_PATH",
        "TELEGRAM_BOT_TOKEN",
        "Persistent=true",
    ]
    combined = "\n".join([install, telegram, child_profile, roadmap, readme])
    for snippet in required_snippets:
        assert snippet in combined


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


def test_child_profile_docs_support_age_staged_full_agent_gateway() -> None:
    docs = read_repo_file("docs/setup-child-profile.md")
    safety = read_repo_file("docs/child-safety-model.md")
    template = read_repo_file("templates/child-profile/config-snippet.yaml")
    script = read_repo_file("scripts/setup-child-profile.sh")
    soul = read_repo_file("templates/child-profile/SOUL.md")
    service_script = read_repo_file("scripts/install-child-gateway-service.sh")

    for text in (docs, safety, template, script, soul, service_script):
        assert_public_safe_text(text)

    required_doc_snippets = [
        "full child-facing Hermes Agent",
        "hermes-gateway-learnbuddy-child.service",
        "scripts/install-child-gateway-service.sh",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_FREE_RESPONSE_CHATS",
        "capability levels",
        "locked",
        "guided",
        "curious",
        "teen-supervised",
        "downgrade",
        "parent approval",
        "audit",
    ]
    for snippet in required_doc_snippets:
        assert snippet in docs
        if snippet not in {"scripts/install-child-gateway-service.sh", "TELEGRAM_BOT_TOKEN", "TELEGRAM_FREE_RESPONSE_CHATS"}:
            assert snippet in safety

    required_template_snippets = [
        "capability_level: guided",
        "learnbuddy_child",
        "allowed_optional_toolsets",
        "parent_approval_required: true",
        "audit_summary_for_parent: true",
        "forbidden_toolsets",
        "terminal",
        "code_execution",
        "homeassistant",
        "messaging",
    ]
    for snippet in required_template_snippets:
        assert snippet in template

    required_script_snippets = [
        "--capability-level LEVEL",
        "locked|guided|curious|teen-supervised",
        "case \"$CAPABILITY_LEVEL\"",
        "PYTHON_BIN",
        "templates/child-profile/SOUL.md",
        "known_plugin_toolsets",
        "disabled_toolsets",
        "copy_default_model_config_if_needed",
        "no provider authentication failure",
        "hermes-gateway-${PROFILE}.service",
        "learnbuddy_child",
    ]
    for snippet in required_script_snippets:
        assert snippet in script

    required_soul_snippets = [
        "learnbuddy_child_submit_answer",
        "short answer",
        "multiline text unchanged",
        "learnbuddy_child_request_parent_help",
        "learnbuddy_child_repeat_pending",
        "learnbuddy_child_request_next_exercise",
        "Noch eine",
        "Nochmal",
        "If an exercise is pending, do not free-chat",
    ]
    for snippet in required_soul_snippets:
        assert snippet in soul

    required_service_script_snippets = [
        "--start",
        "--enable",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "TELEGRAM_ALLOWED_CHATS",
        "TELEGRAM_HOME_CHANNEL",
        "TELEGRAM_FREE_RESPONSE_CHATS",
        "PYTHON_BIN",
        "matches the default profile token",
        "ExecStart=${HERMES_BIN} --profile ${PROFILE} gateway run",
        "systemctl --user daemon-reload",
    ]
    for snippet in required_service_script_snippets:
        assert snippet in service_script


def test_docker_compose_assets_support_one_command_dry_run_smoke(tmp_path) -> None:
    compose = read_repo_file("docker-compose.yml")
    dockerfile = read_repo_file("Dockerfile")
    dockerignore = read_repo_file(".dockerignore")
    entrypoint = read_repo_file("scripts/docker-entrypoint.sh")
    docs = read_repo_file("docs/quickstart-docker.md")
    readme = read_repo_file("README.md")
    install = read_repo_file("INSTALL.md")
    gitignore = read_repo_file(".gitignore")

    for text in (compose, dockerfile, dockerignore, entrypoint, docs):
        assert_public_safe_text(text)

    required_compose_snippets = [
        "learnbuddy:",
        "learnbuddy-smoke:",
        "profiles:",
        "smoke",
        "LEARNBUDDY_CONFIG_PATH=/app/config/learnbuddy.yaml",
        "LEARNBUDDY_DATA_DIR=/app/data",
        "./learnbuddy-docker/config:/app/config",
        "./learnbuddy-docker/data:/app/data",
        "./learnbuddy-docker/backups:/app/backups",
        "delivery.mode=dry_run",
        "compose_smoke=ok",
    ]
    for snippet in required_compose_snippets:
        assert snippet in compose

    required_dockerfile_snippets = [
        "FROM python:3.12-slim",
        "pip install --no-cache-dir -e .",
        "scripts/docker-entrypoint.sh",
        "ENTRYPOINT",
        "CMD",
    ]
    for snippet in required_dockerfile_snippets:
        assert snippet in dockerfile

    for pattern in (
        ".git",
        ".venv",
        ".family/",
        "learnbuddy.db",
        "*.sqlite",
        "*.sqlite3",
        "*.local.yaml",
        "*.local.json",
        "learnbuddy-docker/",
        "data/",
        "*.zip",
    ):
        assert pattern in dockerignore
    assert "learnbuddy-docker/" in gitignore

    required_doc_snippets = [
        "Docker Compose quickstart",
        "docker compose up --build learnbuddy",
        "docker compose --profile smoke up --build --abort-on-container-exit learnbuddy-smoke",
        "delivery.mode: dry_run",
        "compose_smoke=ok",
        "No Telegram message is sent",
        "learnbuddy-docker/config",
        "learnbuddy-docker/data",
        "learnbuddy-docker/backups",
    ]
    for snippet in required_doc_snippets:
        assert snippet in docs
    assert "docs/quickstart-docker.md" in readme
    assert "Docker Compose quickstart" in install

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "learnbuddy.log"
    fake_learnbuddy = fake_bin / "learnbuddy"
    fake_learnbuddy.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        f"log = pathlib.Path({str(log)!r})\n"
        "log.write_text(log.read_text() + ' '.join(sys.argv[1:]) + '\\n' if log.exists() else ' '.join(sys.argv[1:]) + '\\n')\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'setup':\n"
        "    cfg = pathlib.Path(sys.argv[sys.argv.index('--config') + 1])\n"
        "    data = pathlib.Path(sys.argv[sys.argv.index('--data-dir') + 1])\n"
        "    cfg.parent.mkdir(parents=True, exist_ok=True)\n"
        "    data.mkdir(parents=True, exist_ok=True)\n"
        "    cfg.write_text('delivery:\\n  mode: dry_run\\n', encoding='utf-8')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    fake_learnbuddy.chmod(0o755)
    config_path = tmp_path / "config/learnbuddy.yaml"
    data_dir = tmp_path / "data"
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["LEARNBUDDY_CONFIG_PATH"] = str(config_path)
    env["LEARNBUDDY_DATA_DIR"] = str(data_dir)

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/docker-entrypoint.sh"), "doctor", "--config", str(config_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    calls = log.read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "setup --config" in calls
    assert "--data-dir" in calls
    assert "doctor --config" in calls
    assert config_path.exists()


def test_public_alpha_scope_is_telegram_first_and_defers_web_api_app() -> None:
    expectations = {
        "README.md": [
            "Current alpha scope: Telegram-first",
            "Web/PWA, API, and iOS are later surfaces over the same core operations",
        ],
        "INSTALL.md": [
            "Alpha install path is Telegram-first",
            "Do not start with Web/PWA, generic API, or iOS work for the 0.1 alpha",
        ],
        "docs/quickstart-telegram.md": [
            "Telegram is the current alpha product surface",
            "Web/PWA, API, and iOS clients are later surfaces",
        ],
        "docs/extraction-roadmap.md": [
            "Telegram-first alpha scope",
            "Dashboard, Web/PWA, generic API, and iOS stay out of the 0.1 alpha critical path",
        ],
        "docs/ios-roadmap.md": [
            "iOS is not part of the 0.1 alpha",
            "Web/PWA, API, and iOS are later surfaces over the Telegram-proven core",
        ],
    }

    for relative_path, snippets in expectations.items():
        text = read_repo_file(relative_path)
        assert_public_safe_text(text)
        for snippet in snippets:
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


def test_public_grade5_curriculum_pack_matches_vision_parity_scope() -> None:
    fixture = ROOT / "src" / "learnbuddy_core" / "exercise_packs" / "de" / "bavaria-realschule-grade-5.jsonl"
    rows = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]
    subjects = {subject: sum(1 for row in rows if row.get("subject") == subject) for subject in {"math", "german", "english"}}
    topics = {(row.get("subject"), row.get("topic")) for row in rows}

    assert len(rows) == 80
    assert subjects == {"math": 40, "german": 20, "english": 20}
    assert len(topics) >= 18
    assert all(row.get("id", "").startswith("de-by-rs5-") for row in rows)
    assert all(row.get("school_context", {}).get("country_state") == "Bayern" for row in rows)
    assert all(row.get("school_context", {}).get("school_type") == "Realschule" for row in rows)
    assert all(row.get("school_context", {}).get("grade") == 5 for row in rows)
    assert any(row.get("type") == "calculation_batch" for row in rows)
    assert any(row.get("type") == "batch" for row in rows)
    for row in rows:
        assert row.get("prompt")
        assert row.get("answer") is not None or row.get("expected_answers")
        assert_public_safe_text(json.dumps(row, ensure_ascii=False))


def test_install_guide_covers_hermes_and_learnbuddy_setup() -> None:
    text = read_repo_file("INSTALL.md")
    required_snippets = [
        "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash",
        "hermes setup",
        "git clone https://github.com/Cesarus85/learnbuddy-hermes.git",
        "python -m pip install -e '.[test]'",
        "learnbuddy setup",
        "learnbuddy seed --pack de/bavaria-realschule-grade-5",
        "learnbuddy doctor",
        "learnbuddy schedule-exercise",
        "learnbuddy material add-text",
        "learnbuddy material add-file",
        "LEARNBUDDY_MATERIAL_OCR_COMMAND",
        "learnbuddy material approve",
        "material-sets.jsonl",
        "learnbuddy plan create",
        "learnbuddy plan status",
        "learnbuddy dispatch-plan",
        "learnbuddy next --deliver",
        "learnbuddy deliver-pending",
        "learnbuddy report --notify",
        "learnbuddy weekly-status --notify",
        "safety.queue_max",
        "docs/production-migration-checklist.md",
        "delivery.mode: dry_run",
        "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN",
        "hermes plugins",
        "learnbuddy_child",
        "scripts/setup-child-profile.sh",
        "scripts/install-dispatch-timer.sh",
        "pytest -q",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_demo_flow_documents_full_public_smoke_path() -> None:
    text = read_repo_file("docs/demo-flow.md")
    required_snippets = [
        "learnbuddy setup",
        "learnbuddy seed --pack de/bavaria-realschule-grade-5",
        "learnbuddy doctor",
        "learnbuddy queue",
        "learnbuddy schedule-exercise",
        "learnbuddy material add-text",
        "learnbuddy material add-file",
        "LEARNBUDDY_MATERIAL_OCR_COMMAND",
        "learnbuddy material approve",
        "material-sets.jsonl",
        "learnbuddy plan create",
        "learnbuddy plan status",
        "learnbuddy dispatch-plan",
        "learnbuddy next --deliver",
        "learnbuddy deliver-pending",
        "learnbuddy answer",
        "learnbuddy weekly-status --notify",
        "learnbuddy report --notify",
        "learnbuddy backup",
        "learnbuddy restore",
        "delivery.mode: dry_run",
        "examples/exercises/de/grade-5-mixed.jsonl",
    ]
    for snippet in required_snippets:
        assert snippet in text


def test_production_migration_checklist_is_public_safe_and_covers_cutover_gates() -> None:
    text = read_repo_file("docs/production-migration-checklist.md")
    required_snippets = [
        "Read-only inventory",
        "delivery.mode: dry_run",
        "safety.queue_max",
        "queue_full",
        "learnbuddy backup",
        "learnbuddy doctor",
        "learnbuddy weekly-status",
        "parent-only `learnbuddy_learning`",
        "child-only `learnbuddy_child`",
        "production_migration_smoke=ok",
    ]
    assert_public_safe_text(text)
    for snippet in required_snippets:
        assert snippet in text


def test_weekly_status_timer_installer_writes_expected_systemd_units(tmp_path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {systemctl_log}\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/install-weekly-status-timer.sh"),
            "--profile",
            "demo",
            "--config",
            "/tmp/learnbuddy.yaml",
            "--env-file",
            "/tmp/learnbuddy.env",
            "--on-calendar",
            "Sun 18:30",
            "--enable",
            "--start",
            "--python",
            sys.executable,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    service = tmp_path / ".config/systemd/user/learnbuddy-weekly-status-demo.service"
    timer = tmp_path / ".config/systemd/user/learnbuddy-weekly-status-demo.timer"
    service_text = service.read_text(encoding="utf-8")
    timer_text = timer.read_text(encoding="utf-8")
    systemctl_calls = systemctl_log.read_text(encoding="utf-8")

    assert "learnbuddy weekly-status --notify" in result.stdout
    assert "Environment=LEARNBUDDY_CONFIG_PATH=/tmp/learnbuddy.yaml" in service_text
    assert "Environment=LEARNBUDDY_ENV_FILE=/tmp/learnbuddy.env" in service_text
    assert f"ExecStart={sys.executable} -m learnbuddy_core.cli weekly-status --notify --config /tmp/learnbuddy.yaml" in service_text
    assert "OnCalendar=Sun 18:30" in timer_text
    assert "Persistent=true" in timer_text
    assert "daemon-reload" in systemctl_calls
    assert "enable learnbuddy-weekly-status-demo.timer" in systemctl_calls
    assert "start learnbuddy-weekly-status-demo.timer" in systemctl_calls
