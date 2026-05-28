# Install LearnBuddy Hermes

This guide is written for a technical parent or an operator running a fresh local Linux/VPS setup. It covers both pieces:

1. Install and configure Hermes Agent.
2. Install LearnBuddy from this repository and run the safe dry-run lifecycle.

The default path sends nothing to Telegram and uses no child production data. Keep `delivery.mode: dry_run` until the local smoke test is green.

Alpha install path is Telegram-first. Install Hermes, run the local dry-run lifecycle, then enable the Telegram child/parent adapters deliberately. Do not start with Web/PWA, generic API, or iOS work for the 0.1 alpha; those are later surfaces over the same bounded core after the Telegram path is proven.

## Requirements

- Linux, macOS, or WSL with Python 3.11+
- `git`
- network access for installing Hermes and Python packages
- one configured Hermes model provider before real agent use
- optional later: dedicated Telegram bots for child and parent delivery

## 1. Install Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

Open a new shell if the installer changed your `PATH`, then run:

```bash
hermes setup
hermes doctor
```

During `hermes setup`, configure at least one model provider. LearnBuddy itself can be smoke-tested without model calls, but a real Hermes child/parent profile needs a working model.

## 2. Clone LearnBuddy

```bash
mkdir -p ~/learnbuddy
cd ~/learnbuddy
git clone https://github.com/Cesarus85/learnbuddy-hermes.git
cd learnbuddy-hermes
```

For the latest tagged alpha release:

```bash
git checkout v0.1.2-alpha
```

## 3. Optional fast path: Docker Compose quickstart

If Docker Compose is available, you can run the safe dry-run doctor without creating a Python venv first:

```bash
docker compose up --build learnbuddy
```

Then run the controlled smoke path:

```bash
docker compose --profile smoke up --build --abort-on-container-exit learnbuddy-smoke
```

Expected markers:

```text
delivery.mode=dry_run
compose_smoke=ok
```

This creates local runtime folders under `learnbuddy-docker/config`, `learnbuddy-docker/data`, and `learnbuddy-docker/backups`. They are git-ignored and may become private once you use real family data. See [`docs/quickstart-docker.md`](docs/quickstart-docker.md) for Compose CLI examples and the Telegram opt-in boundary.

## 4. Create an isolated Python environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

Verify the CLI and tests:

```bash
learnbuddy --help
pytest -q
```

## 5. Create public-safe local config

```bash
learnbuddy setup \
  --config ./learnbuddy.yaml \
  --data-dir ./data/learnbuddy \
  --child-id learner \
  --child-name Learner \
  --agent-name LearnBuddy
```

The generated config should keep delivery disabled for the first run:

```yaml
delivery.mode: dry_run
```

`learnbuddy.yaml`, `data/`, restore folders, and backup zips are ignored by git by default because they become private local runtime artifacts.

The generated `safety.queue_max` limits follow-up tasks while one exercise is open. This mirrors the production-safety rule that parent/chat automation must not pile up unlimited queued tasks.

## 6. Run the full dry-run smoke test

This step covers `learnbuddy schedule-exercise`, `learnbuddy plan`, `learnbuddy dispatch-plan`, `learnbuddy deliver-pending`, and `learnbuddy report --notify` in the full smoke path.

```bash
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy schedule-exercise --config ./learnbuddy.yaml --subject math --prompt "8 + 9?" --answer "17" --due-at "2099-01-01T10:30:00+01:00"
learnbuddy plan create --config ./learnbuddy.yaml --title "Mathe-Woche" --subject math --daily-goal 1
learnbuddy dispatch-plan --config ./learnbuddy.yaml
learnbuddy deliver-pending --config ./learnbuddy.yaml
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy plan status --config ./learnbuddy.yaml
learnbuddy status --config ./learnbuddy.yaml
learnbuddy help-request --config ./learnbuddy.yaml --reason "Learner needs a parent hint." --notify
learnbuddy watch-telegram-answers --config ./learnbuddy.yaml --env-file ./learnbuddy.env
learnbuddy report --config ./learnbuddy.yaml --notify
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
```

Expected first-run behavior:

- `doctor` is ok.
- child delivery result is `dry_run`.
- parent notification result is `dry_run`.
- restore succeeds into a fresh directory.

A fuller walkthrough lives in [`docs/demo-flow.md`](docs/demo-flow.md). For existing private deployments, use [`docs/production-migration-checklist.md`](docs/production-migration-checklist.md) before touching production.

## 7. Optional: use the synthetic exercise fixture

Public demo exercises live here:

```text
examples/exercises/de/grade-5-mixed.jsonl
```

They are intentionally synthetic and cover math, German, and English. They are examples, not a curriculum.

## 8. Optional: install the Hermes plugin wrapper locally

The CLI works directly from the Python package. To expose the LearnBuddy plugin wrapper to a Hermes profile, install the plugin directory into that profile's plugin folder.

Default profile example:

```bash
mkdir -p ~/.hermes/plugins/learnbuddy-learning
rsync -a --delete plugins/learnbuddy-learning/ ~/.hermes/plugins/learnbuddy-learning/
python -m pip install -e .
hermes plugins list
hermes plugins enable learnbuddy-learning || true
hermes config set platform_toolsets.telegram '["hermes-telegram","learnbuddy_learning"]'
hermes plugins list
```

Live parent-gateway hardening path (recommended for Telegram alpha):

```bash
scripts/setup-parent-profile.sh \
  --profile learnbuddy-parent \
  --config ./learnbuddy.yaml \
  --env-file ./learnbuddy.env
```

That writes `templates/parent-profile/SOUL.md`, installs the `learnbuddy-learning` plugin, locks Telegram routing to `learnbuddy_learning`, records `learnbuddy_child` as a known-but-not-exposed plugin toolset, and gives the agent explicit instructions to call `learnbuddy_parent_command_contracts` before handling LearnBuddy parent commands. `learnbuddy_create_and_send_exercise` requires a concrete prompt plus `answer_or_expected_answers`; multi-part arithmetic prompts such as `Frage Learner folgende Aufgaben` must pass ordered `expected_answers` before anything is sent to the child.

For unattended gateway use, set defaults in the profile environment instead of relying on the model to pass paths on every tool call:

```text
LEARNBUDDY_CONFIG_PATH=/absolute/path/to/learnbuddy.yaml
LEARNBUDDY_ENV_FILE=/absolute/path/to/learnbuddy.env
```

`LEARNBUDDY_ENV_FILE` is optional and should be mode `600`; it can hold the Telegram variables named by the YAML. Existing process environment values win over the file. The plugin also exposes `learnbuddy_create_and_send_exercise` as a one-call parent orchestration helper: create exercise → open it → deliver to the child adapter → persist delivery metadata. `learnbuddy_schedule_exercise` creates a concrete one-shot task for later delivery; it requires `due_at` plus `answer_or_expected_answers`, stores the task in scheduled runtime data, and relies on `learnbuddy_dispatch_plan` to make it child-visible when due. `learnbuddy_dispatch_plan` is scheduler-safe for one due automatic or scheduled exercise, respecting allowed hours and current pending state. `daily_auto_limit` gates automatic selection; explicit parent-scheduled due exercises wait behind pending work, then dispatch even if the automatic daily limit is already used. `learnbuddy_daily_parent_status` sends at most one local-day parent status, respects `pause_today`, skips duplicate sends, and skips empty days unless `include_empty=true`; `learnbuddy_parent_automation_control` handles `heute pausieren`/resume/status commands. `learnbuddy_deliver_pending_exercise` repairs/resends the current pending prompt when the learner did not receive it. It also exposes `learnbuddy_parent_help_request` as the public-safe parent-help path: it records a local help request and only notifies parents with `notify=true`. Hermes receives guided JSON schemas for the LearnBuddy tools, which keeps parent-chat commands bounded: create/send needs a concrete prompt, scheduled dispatch is policy-bounded, repair/resend is explicit, help/report/status pushes require explicit notification flags, and status reads do not send messages.

The parent/main profile can use the broad `learnbuddy_learning` toolset for parent/admin commands. A child-facing profile should be created separately as a full child-facing Hermes Agent with the `learnbuddy_child` baseline plus explicit capability levels (`locked`, `guided`, `curious`, `teen-supervised`). Do not clone a parent/admin profile wholesale; upgrades need parent approval, audit, and a downgrade path.

Fast path:

```bash
scripts/setup-child-profile.sh \
  --profile learnbuddy-child \
  --config ./learnbuddy.yaml \
  --capability-level guided
```

Optional model setup:

```bash
scripts/setup-child-profile.sh \
  --profile learnbuddy-child \
  --config ./learnbuddy.yaml \
  --capability-level guided \
  --provider your-provider \
  --model your-model
```

Manual shape:

```bash
hermes profile create learnbuddy-child --no-skills --no-alias
hermes --profile learnbuddy-child config set model.provider your-provider
hermes --profile learnbuddy-child config set model.default your-model
hermes --profile learnbuddy-child plugins enable learnbuddy-learning || true
hermes --profile learnbuddy-child config set platform_toolsets.telegram '["learnbuddy_child","tts","vision"]'  # guided capability level
hermes --profile learnbuddy-child config check
```

Before any real child uses it, verify the child profile has no terminal, file, code execution, smart-home, purchasing, generic messaging, or unapproved broad skills/delegation/cron tools enabled. See [`docs/setup-child-profile.md`](docs/setup-child-profile.md). If you start the full child-facing gateway, keep it separate from the parent gateway; install the intended child service with:

```bash
scripts/install-child-gateway-service.sh --profile learnbuddy-child
```

Start/enable it only after the child profile `.env` has a dedicated `TELEGRAM_BOT_TOKEN`, allowlists, `TELEGRAM_HOME_CHANNEL`, and `TELEGRAM_FREE_RESPONSE_CHATS`:

```bash
scripts/install-child-gateway-service.sh --profile learnbuddy-child --enable --start
```

Optional scheduled-exercise dispatch timer:

```bash
scripts/install-dispatch-timer.sh \
  --profile learnbuddy-parent \
  --config ./learnbuddy.yaml \
  --env-file ./learnbuddy.env \
  --on-unit-active-sec 5min \
  --python ./.venv/bin/python \
  --enable --start
```

The generated systemd user timer runs `learnbuddy dispatch-plan` repeatedly. This is the delivery belt for parent-created timed tasks from `learnbuddy schedule-exercise` / `learnbuddy_schedule_exercise`: scheduling persists the row, but dispatching is what opens the session, sends it to the child adapter, writes delivery metadata, and marks the scheduled item dispatched. Keep this timer separate from the daily-status timer; `learnbuddy daily-status --notify` reports to parents and will not deliver due child tasks.

Optional daily parent status timer:

```bash
scripts/install-daily-status-timer.sh \
  --profile learnbuddy-parent \
  --config ./learnbuddy.yaml \
  --env-file ./learnbuddy.env \
  --on-calendar 21:00 \
  --python ./.venv/bin/python \
  --enable --start
```

The installer auto-detects a project `.venv/bin/python` or sibling `../.venv/bin/python` when run from a source checkout; pass `--python` explicitly for nonstandard venv layouts. The generated systemd user timer runs `learnbuddy daily-status --notify`. The command is safe for unattended use: it reports started tasks, latest answers, attempts, and subject totals; skips truly empty days by default; sends at most once per local date; and respects parent `heute pausieren` / `learnbuddy_parent_automation_control action=pause_today`.

Optional Sunday weekly report with compact recommendations:

```bash
scripts/install-weekly-status-timer.sh \
  --config ./learnbuddy.yaml \
  --on-calendar "Sun 19:00" \
  --python ./.venv/bin/python \
  --enable --start
```

This writes a systemd user timer that runs `learnbuddy weekly-status --notify`. It summarizes the current local week, includes next-week recommendations, skips empty weeks by default, sends at most once per week, and uses the same parent automation pause guard as daily status.

## 9. Optional: Telegram delivery

Keep Telegram off until the dry-run flow works.

Create dedicated bots and store real values in your local environment or process manager. The YAML should contain only variable names:

```text
LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_CHILD_CHAT_ID
LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_PARENT_CHAT_ID
```

Then switch config to:

```yaml
delivery:
  mode: telegram
  telegram:
    child_bot_env: LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN
    allowed_child_chat_id_env: LEARNBUDDY_ALLOWED_CHILD_CHAT_ID
  parents:
    - type: telegram
      bot_token_env: LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN
      target_env: LEARNBUDDY_ALLOWED_PARENT_CHAT_ID
```

Run:

```bash
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy schedule-exercise --config ./learnbuddy.yaml --subject math --prompt "8 + 9?" --answer "17" --due-at "2099-01-01T10:30:00+01:00"
learnbuddy dispatch-plan --config ./learnbuddy.yaml --subject math
learnbuddy deliver-pending --config ./learnbuddy.yaml
# Manual parent-open path: learnbuddy next --deliver
# learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy watch-telegram-answers --config ./learnbuddy.yaml --env-file ./learnbuddy.env
learnbuddy report --config ./learnbuddy.yaml --notify
```

`doctor` reports missing variable names, not secret values, and flags unwritable runtime files such as a root-owned `scheduled_exercises.jsonl` before timers fail mid-dispatch. `queue_max` caps follow-up tasks behind an active pending exercise, returning `queue_full` instead of silently piling up unlimited work. `schedule-exercise` records a concrete timed task; it does not send by itself. `dispatch-plan` is safe to run from cron/systemd: it opens and delivers at most one due scheduled or automatic exercise when allowed-hours policy permits it and no exercise is already pending. `daily_auto_limit` applies to automatic plan selection, not to explicit parent-scheduled due rows. Use `scripts/install-dispatch-timer.sh` for the recurring dispatcher path. `watch-telegram-answers` is intentionally one-shot: run it from cron/systemd every minute if you want child replies in the Kids bot to be evaluated automatically, with feedback sent back to the child and a parent result notification. When a correct/exhausted answer promotes a queued exercise, the watcher also delivers the promoted prompt to the child, so queued parent tasks do not sit silently in the background. If a pending exercise has no successful child-delivery metadata, the watcher repairs that by sending the current prompt before waiting for another answer; `learnbuddy deliver-pending` gives the same repair path as an explicit operator command.

## 10. VPS notes

For VPS installs, use a dedicated non-root user and a dedicated directory such as:

```text
/opt/learnbuddy/
  repo/
  .venv/
  config/
  data/
  backups/
```

Recommended VPS flow:

1. install Hermes and configure a model provider
2. clone this repository or fetch a release artifact
3. install LearnBuddy into an isolated venv
4. run the dry-run smoke test
5. test backup and restore
6. only then configure Telegram or a future web/API surface

See [`docs/quickstart-vps.md`](docs/quickstart-vps.md).

## Can an autonomous Hermes agent install this from the repo link?

A Hermes agent with terminal and file tools can follow this guide from the repository link. For alpha installs, a human operator should still supervise credential entry, child-profile tool restrictions, Telegram bot setup, and the first real delivery test.

Best practice for alpha:

- let the agent do the mechanical terminal work
- keep secrets entered by the operator, not pasted into chat logs
- review `learnbuddy.yaml` before real delivery
- run `learnbuddy doctor` and the dry-run smoke before Telegram mode
- keep backups private

## Troubleshooting

- `learnbuddy: command not found`: activate `.venv` or reinstall with `python -m pip install -e '.[test]'`.
- `doctor` says Telegram is not configured: keep `dry_run` or set the required environment variables outside git.
- restore refuses to overwrite: use a fresh restore directory or pass `--force` intentionally.
- tests fail after local edits: run `git status`, revert generated runtime artifacts, then rerun `pytest -q`.
