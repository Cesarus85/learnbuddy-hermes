# Telegram Quickstart

This guide connects LearnBuddy to Telegram without storing credentials in git.

Telegram is the current alpha product surface. The 0.1 alpha should prove the parent command contracts, child delivery state, answer watcher, help/repeat/next controls, and parent notifications here first. Web/PWA, API, and iOS clients are later surfaces over the same LearnBuddy core, not parallel alpha targets.

For a network-free first run, start with [`demo-flow.md`](demo-flow.md). Telegram should be enabled only after the local `dry_run` lifecycle is green.

## 1. Install and run the dry-run setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'

learnbuddy setup \
  --config ./learnbuddy.yaml \
  --data-dir ./data/learnbuddy \
  --child-id learner \
  --child-name Learner \
  --agent-name LearnBuddy

learnbuddy doctor --config ./learnbuddy.yaml
```

The generated config uses:

```yaml
delivery:
  mode: dry_run
```

Keep this mode until you have verified the basic queue/answer/report flow.

## 2. Create dedicated Telegram bots

Recommended separation:

- one child-facing bot for exercises and answers
- one parent-facing bot for summaries and admin messages

Do not reuse a parent/admin bot as the child bot. Do not commit bot tokens, chat IDs, exported chats, screenshots with IDs, or `.env` files.

## 3. Store Telegram values in environment variables

Use a local shell, process manager, or secret store. Configure these variable names with your own private values:

```text
LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_CHILD_CHAT_ID
LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_PARENT_CHAT_ID
```

Keep real values out of docs and git.

## 4. Switch config to Telegram mode

Edit `learnbuddy.yaml`:

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

## 5. Validate before sending

```bash
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy dispatch-plan --config ./learnbuddy.yaml --subject math
learnbuddy deliver-pending --config ./learnbuddy.yaml
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy daily-status --config ./learnbuddy.yaml --notify
learnbuddy report --config ./learnbuddy.yaml --notify
```

Expected behavior:

- `doctor` prints variable names only, never secret values.
- `dispatch-plan` opens and sends one automatic exercise only when policy allows it (`daily_auto_limit`, `allowed_hours`, no current pending item).
- `next --deliver` remains the manual parent-open path and records delivery metadata on the pending session.
- `deliver-pending` repairs/resends the current pending prompt if the learner never saw it.
- `report --notify` sends a parent summary through the parent adapter when configured.
- `daily-status --notify` sends at most one local-day parent status with started tasks, latest answers, attempt history, and subject totals. It skips truly empty days by default and respects `automation pause-today` / parent `heute pausieren` controls. Install it with `scripts/install-daily-status-timer.sh` only after dry-run smoke tests are green.
- `watch-telegram-answers` evaluates Kids-bot replies; when there is no answer it repairs any undelivered pending prompt, and after a correct/exhausted answer it promotes and delivers the next queued exercise automatically.
- `learnbuddy_parent_command_contracts` documents the supported parent Telegram operation mapping: status, report, resend pending, scheduled dispatch, and create/send exercise.
- Child control messages are handled before answer evaluation: `Nochmal`/`nochmal senden` resends the pending prompt without incrementing attempts; `Hilfe`/`Ich weiß nicht` records a bounded parent-help request, confirms this to the child, and notifies parents when parent notifications are enabled; `Noch eine`/`Noch eine Aufgabe` is bounded by the same scheduler policy as `dispatch-plan`, never creates free-form tasks, and notifies parents with a help request when the child asks for another task but LearnBuddy cannot open one.
- Missing or invalid Telegram configuration returns a safe error/not-configured status rather than leaking credentials.

## Safety checklist

- Parent/main profile may use `learnbuddy_learning` for admin commands.
- Direct child chat uses a separate Hermes profile with `learnbuddy_child`; see [`setup-child-profile.md`](setup-child-profile.md).
- Child profile has no terminal, file, code execution, smart-home, purchasing, broad skills/delegation/cron, or generic messaging tools.
- Parent controls setup and credentials.
- Exercises are age-appropriate and synthetic until you intentionally enter family-specific content locally.
- Backups are treated as private learning data.
- If anything routes to the wrong recipient, stop and fix routing before continuing.
