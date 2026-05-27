# Dedicated Child Profile Quickstart

This guide is for families who already use Hermes Agent and want a separate full child-facing Hermes Agent for LearnBuddy.

The conservative alpha watcher is still useful as a repair/fallback path, but the recommended growing-child architecture is a real child Hermes profile with its own Telegram gateway. That lets parents start locked down and gradually enable more native Hermes features as the child gets older and demonstrates responsible use.

Recommended architecture:

```text
Parent/main Hermes profile  -> learnbuddy_learning toolset
Child Hermes profile        -> learnbuddy_child + staged optional toolsets
LearnBuddy runtime data     -> shared local LearnBuddy data directory
Telegram child bot          -> dedicated bot token and allowlisted child chat
Telegram parent bot         -> separate parent/admin bot
Child gateway service       -> hermes-gateway-learnbuddy-child.service
```

A single main Hermes agent can safely handle parent/admin learning commands. A child who chats directly with LearnBuddy should use a separate profile and gateway.

## Full child-facing Hermes Agent

The child bot is intended to become a **full child-facing Hermes Agent**, not just a form submitter. The baseline stays bounded by LearnBuddy, but the profile can grow through explicit parent approval.

Core rule: the child profile may gain learning features, never household/admin powers by accident. All upgrades must be reversible; downgrade and lockdown should be one config/script step.

## Capability levels

The shipped presets are the public capability levels and are deliberately conservative:

- `locked` — only `learnbuddy_child`; answer pending exercises, check status, request parent help.
- `guided` — `learnbuddy_child`, `tts`, `vision`; good default for younger children who may send voice notes or worksheet photos.
- `curious` — guided plus narrow `search`; allows supervised learning research without file/terminal/system access.
- `teen-supervised` — curious plus `skills`, `delegation`, and `cronjob` for supervised learning organization. Parents should review this level before use.

Every preset keeps these forbidden:

- terminal
- file access
- code execution
- Home Assistant / smart home control
- generic messaging tools
- purchasing or external action tools

## Parent approval, audit, and downgrade

Parents should treat feature changes like permissions on a real device:

- Upgrade only after parent approval.
- Review what changed before starting/restarting the child gateway.
- Keep an audit note/report of active capability level and enabled optional toolsets.
- Use downgrade immediately if behavior gets confusing, too broad, or age-inappropriate.
- Prefer the smallest level that supports the child's current learning goal.

The template file `templates/child-profile/config-snippet.yaml` records:

- `capability_level`
- `allowed_optional_toolsets`
- `parent_approval_required: true`
- `audit_summary_for_parent: true`
- `forbidden_toolsets`

## What the child profile may do

Expose `learnbuddy_child` plus the optional toolsets for the chosen capability level.

`learnbuddy_child` currently contains:

- `learnbuddy_child_submit_answer` — answer the current pending exercise
- `learnbuddy_child_status` — check whether an exercise is pending
- `learnbuddy_child_request_parent_help` — ask the configured parent for learning help

Do not expose parent/admin orchestration tools to the child profile.

## What the child profile must not have

Forbidden by default and in all shipped presets:

- terminal
- file access
- code execution
- Home Assistant / smart home control
- generic messaging tools
- purchasing or external action tools

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
  --config ./learnbuddy.yaml \
  --capability-level guided
```

Optional model configuration:

```bash
scripts/setup-child-profile.sh \
  --profile learnbuddy-child \
  --config ./learnbuddy.yaml \
  --capability-level locked \
  --provider your-provider \
  --model your-model
```

The script:

- creates the Hermes profile if missing
- installs the LearnBuddy plugin into that profile
- enables the `learnbuddy_child` Telegram toolset plus the selected capability-level optional toolsets
- writes only local path defaults into the profile `.env`
- prints the expected child gateway service name, e.g. `hermes-gateway-learnbuddy-child.service`
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
scripts/setup-child-profile.sh --profile learnbuddy-child --config ./learnbuddy.yaml --env-file ./learnbuddy.env --capability-level guided --skip-install
```

## 4. Install the child profile gateway service

The child gateway is a separate systemd user service for the child Hermes profile. Install the unit first; start it only after the dedicated child Telegram bot token and allowlists are in the child profile `.env`.

Checklist before starting the gateway:

```bash
hermes --profile learnbuddy-child plugins list
hermes --profile learnbuddy-child config check
hermes --profile learnbuddy-child tools list
```

Confirm the child profile exposes the selected capability level and does not expose terminal/file/code execution/generic messaging tools.

Install the dedicated service:

```bash
scripts/install-child-gateway-service.sh --profile learnbuddy-child
```

The default service name is:

```text
hermes-gateway-learnbuddy-child.service
```

Before `--start` or `--enable`, the installer refuses unsafe gateway promotion unless the child profile `.env` contains:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USERS or TELEGRAM_ALLOWED_CHATS
TELEGRAM_HOME_CHANNEL
TELEGRAM_FREE_RESPONSE_CHATS
```

It also refuses to start if the child bot token matches the default profile Telegram bot token. That check is intentionally blunt; reusing the parent/default bot for a child profile is how you create a haunted house with push notifications.

Once the dedicated child BotFather token and allowlists are set:

```bash
scripts/install-child-gateway-service.sh --profile learnbuddy-child --enable --start
systemctl --user status hermes-gateway-learnbuddy-child.service
```

If your Hermes install creates a different per-profile service name, document it in your private runbook and keep the parent and child gateways separate.

## 5. Parent/main profile

The parent/main profile can use the broader `learnbuddy_learning` toolset for parent/admin commands:

- create and send exercises
- queue exercises
- request reports
- inspect status
- process parent-help messages
- review capability level and audit notes
- downgrade the child profile if needed

If you prefer the conservative alpha flow, keep the child bot as a send/answer endpoint and let `learnbuddy watch-telegram-answers` process replies without a free child chat agent. For a growing LearnBuddy child agent, use the dedicated child gateway instead.

## 6. Verification flow

Dry run:

```bash
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy report --config ./learnbuddy.yaml --notify
```

Telegram answer watcher fallback:

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
- Direct child chat: dedicated `learnbuddy-child` profile and child gateway.
- Child profile tools: `learnbuddy_child` plus age-/maturity-appropriate optional toolsets, never the broad parent/admin toolset.
- Capability changes require parent approval, audit, and an easy downgrade path.
