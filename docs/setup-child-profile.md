# Dedicated Child Profile Quickstart

This guide is for families who already use Hermes Agent and want a separate child-facing LearnBuddy agent.

Recommended architecture:

```text
Parent/main Hermes profile  -> learnbuddy_learning toolset
Child Hermes profile        -> learnbuddy_child toolset only
LearnBuddy runtime data     -> shared local LearnBuddy data directory
Telegram child bot          -> dedicated bot token and allowlisted child chat
Telegram parent bot         -> separate parent/admin bot
```

A single main Hermes agent can safely handle parent/admin learning commands. A child who chats directly with LearnBuddy should use a separate locked-down profile.

## What the child profile may do

Expose only the `learnbuddy_child` toolset plus optional child-facing media tools such as `tts` and `vision`.

`learnbuddy_child` currently contains:

- `learnbuddy_child_submit_answer` — answer the current pending exercise
- `learnbuddy_child_status` — check whether an exercise is pending
- `learnbuddy_child_request_parent_help` — ask the configured parent for learning help

Do not expose parent/admin orchestration tools to the child profile.

## What the child profile must not have

Forbidden by default:

- terminal
- file access
- code execution
- Home Assistant / smart home control
- generic messaging tools
- purchasing or external action tools
- broad skills/delegation/cron access unless you have a reviewed child-safety design

## 1. Prepare LearnBuddy core

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
learnbuddy setup --config ./learnbuddy.yaml --data-dir ./data/learnbuddy --child-id learner --child-name Learner --agent-name LearnBuddy
learnbuddy doctor --config ./learnbuddy.yaml
```

Keep `delivery.mode: dry_run` until the basic lifecycle is green.

## 2. Create or update the child profile

Use the helper script:

```bash
scripts/setup-child-profile.sh \
  --profile learnbuddy-child \
  --config ./learnbuddy.yaml
```

Optional model configuration:

```bash
scripts/setup-child-profile.sh \
  --profile learnbuddy-child \
  --config ./learnbuddy.yaml \
  --provider your-provider \
  --model your-model
```

The script:

- creates the Hermes profile if missing
- installs the LearnBuddy plugin into that profile
- enables the narrow `learnbuddy_child` Telegram toolset
- writes only local path defaults into the profile `.env`
- runs `hermes --profile learnbuddy-child config check`

It does **not** write Telegram tokens or chat IDs.

## 3. Add Telegram only after dry-run works

Create a dedicated child bot and a separate parent/admin bot. Store real values in an env file or process manager; do not commit them.

Example env variable names:

```text
LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_CHILD_CHAT_ID
LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN
LEARNBUDDY_ALLOWED_PARENT_CHAT_ID
```

If you keep those values in `./learnbuddy.env`, lock it down:

```bash
chmod 600 ./learnbuddy.env
scripts/setup-child-profile.sh --profile learnbuddy-child --config ./learnbuddy.yaml --env-file ./learnbuddy.env --skip-install
```

## 4. Configure the child profile gateway

Use the normal Hermes gateway setup for the child profile and the dedicated child bot token.

Checklist before starting the gateway:

```bash
hermes --profile learnbuddy-child plugins list
hermes --profile learnbuddy-child config check
hermes --profile learnbuddy-child tools list
```

Confirm the child profile exposes `learnbuddy_child` and does not expose terminal/file/code execution/generic messaging tools.

Then start or restart the gateway for that profile using your normal Hermes service pattern.

## 5. Parent/main profile

The parent/main profile can use the broader `learnbuddy_learning` toolset for parent/admin commands:

- create and send exercises
- queue exercises
- request reports
- inspect status
- process parent-help messages

If you prefer the conservative alpha flow, keep the child bot as a send/answer endpoint and let `learnbuddy watch-telegram-answers` process replies without a free child chat agent.

## 6. Verification flow

Dry run:

```bash
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy report --config ./learnbuddy.yaml --notify
```

Telegram answer watcher:

```bash
learnbuddy watch-telegram-answers --config ./learnbuddy.yaml --env-file ./learnbuddy.env
```

Expected behavior:

- child answers are evaluated against the pending exercise
- feedback goes to the child adapter
- result notifications go to the parent adapter
- no secret values are printed by `doctor`

## Rule of thumb

- Parent/admin commands: main Hermes profile is fine.
- Direct child chat: dedicated `learnbuddy-child` profile only.
- Child profile tools: `learnbuddy_child`, not the broad parent/admin toolset.
