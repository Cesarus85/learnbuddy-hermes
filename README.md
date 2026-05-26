# LearnBuddy Hermes

Self-hosted, parent-controlled learning practice for families, built as a Hermes Agent extension pack.

> Status: `0.1.0-alpha` preparation. The core CLI, dry-run delivery, setup, doctor, backup/restore, examples, and tests are usable for public evaluation. Use synthetic data until you have reviewed the safety and privacy docs for your own family.

## What this is

LearnBuddy is a bounded learning companion that can:

- queue short exercises for a child
- open one pending exercise at a time
- evaluate answers kindly
- limit attempts and give a final explanation when attempts are used up
- track progress in local JSON/JSONL runtime files
- render parent-facing summaries
- record bounded parent-help requests and notify parents only when explicitly requested
- run network-free in `dry_run` mode or via Telegram adapters

## What this is not

- not a replacement for parents, teachers, school, tutoring, or professional advice
- not a hosted child-AI SaaS
- not a general-purpose child chatbot with full system access
- not connected to ads, tracking, telemetry, or analytics
- not a place for production child logs, private chat exports, or real credentials

## Deployment modes

Supported design targets:

1. Homehosting: Raspberry Pi, mini-PC, NAS, Mac mini, or local server.
2. VPS + cloud LLM: useful when a family already uses a cloud model provider.
3. Local LearnBuddy + cloud LLM: child data and orchestration stay local while model calls go to the configured provider.
4. Advanced: VPS LearnBuddy connected to a private/local model endpoint via VPN/Tailscale.

## Current roadmap

- `0.1`: Telegram self-hosted MVP, local CLI lifecycle, setup, doctor, backup/restore, demo fixtures
- `0.2`: VPS/cloud-LLM setup docs and hardening
- `0.3`: Parent dashboard / PWA
- `0.4`: multiple children and parent devices
- `0.5`: iOS companion app

See [`docs/extraction-roadmap.md`](docs/extraction-roadmap.md) for the public-safe extraction plan.

## Safety baseline

The parent/main Hermes profile may use the broader `learnbuddy_learning` toolset for admin tasks such as creating exercises, reading status, and sending reports. A child who chats directly with LearnBuddy should use a separate locked-down Hermes profile with the narrow `learnbuddy_child` toolset.

The child-facing Hermes profile must be least-privilege. Default forbidden toolsets:

- terminal
- file access
- code execution
- smart home / Home Assistant
- generic messaging
- purchases or external actions

Only bounded LearnBuddy tools should be exposed to the child profile.

## Repository layout

```text
plugins/learnbuddy-learning/        Hermes plugin wrapper
src/learnbuddy_core/                shared core logic
scripts/                            helper scripts for profile setup
examples/                           safe example configs
examples/exercises/de/              synthetic exercise fixtures
templates/                          profile/config templates
docs/                               setup, safety, privacy, roadmap, demo flow
tests/                              regression and public-alpha asset tests
```

## Installation

Start with [`INSTALL.md`](INSTALL.md) for the complete Hermes + LearnBuddy setup path.

## Quick start: local dry-run demo

The fastest safe smoke test uses no Telegram token and sends nothing to the network:

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
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy dispatch-plan --config ./learnbuddy.yaml --subject math
learnbuddy deliver-pending --config ./learnbuddy.yaml
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy status --config ./learnbuddy.yaml
learnbuddy help-request --config ./learnbuddy.yaml --reason "Learner needs a parent hint." --notify
learnbuddy watch-telegram-answers --config ./learnbuddy.yaml --env-file ./learnbuddy.env
learnbuddy report --config ./learnbuddy.yaml --notify
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
pytest -q
```

Expected delivery status in this quickstart: `dry_run` for both child delivery and parent notification.

## Demo exercise fixture

Synthetic German grade-5 sample exercises live in:

```text
examples/exercises/de/grade-5-mixed.jsonl
```

They cover `math`, `german`, and `english` and are validated by `tests/test_public_alpha_assets.py`. They are examples, not a curriculum.

See [`docs/demo-flow.md`](docs/demo-flow.md) for a full copy/paste demo using the fixture.

## Telegram configuration

`learnbuddy setup` writes `delivery.mode: dry_run` by default. Telegram mode is opt-in and uses environment variable names, not secret values in YAML:

```yaml
child:
  id: emma
  display_name: Emma
agent:
  name: Lumi
safety:
  max_attempts: 3
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
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

`learnbuddy dispatch-plan` opens and delivers one automatic exercise only when policy allows it (`daily_auto_limit`, `allowed_hours`, no current pending item). `learnbuddy next --deliver` uses the child adapter for manual parent-open flows and persists child-delivery metadata on the pending session. `learnbuddy deliver-pending` repairs/resends the currently pending prompt when a parent reports that the learner never saw it. `learnbuddy report --notify` uses the parent adapter. `learnbuddy watch-telegram-answers` evaluates one Kids-bot answer, sends feedback, repairs any undelivered pending prompt when there is no answer, and if a queued exercise is promoted after a correct/exhausted answer, delivers that next prompt to the child automatically. Child control messages are intentionally narrow: `Nochmal`/`nochmal senden` resends the current pending prompt without counting as an answer, and `Hilfe`/`Ich weiß nicht` creates a bounded parent-help request, confirms this to the child, and notifies parents when parent notifications are enabled. If Telegram env vars are missing, `doctor` reports missing variable names without printing secret values.

For Hermes gateway/plugin use, set profile env defaults so the model can call LearnBuddy tools without repeating local paths:

```text
LEARNBUDDY_CONFIG_PATH=/absolute/path/to/learnbuddy.yaml
LEARNBUDDY_ENV_FILE=/absolute/path/to/learnbuddy.env
```

The plugin's `learnbuddy_create_and_send_exercise` tool is the simplest parent flow: it creates an exercise, opens it, delivers it to the configured child adapter in one bounded call, and stores delivery metadata on the pending session. `learnbuddy_dispatch_plan` is scheduler-safe for one due automatic exercise, and `learnbuddy_deliver_pending_exercise` repairs/resends the currently pending prompt if the learner did not receive it. The plugin publishes guided JSON schemas for Hermes so parent-chat commands stay narrow: create/send needs a concrete child prompt, repair/resend is explicit, status reads are separate, and pushed parent reports require `notify=true` explicitly.

## Docs

- [`docs/quickstart-telegram.md`](docs/quickstart-telegram.md)
- [`docs/setup-child-profile.md`](docs/setup-child-profile.md)
- [`docs/quickstart-vps.md`](docs/quickstart-vps.md)
- [`docs/demo-flow.md`](docs/demo-flow.md)
- [`docs/child-safety-model.md`](docs/child-safety-model.md)
- [`PRIVACY.md`](PRIVACY.md)
- [`SECURITY.md`](SECURITY.md)

## Privacy promise for the project

No real child data, chat IDs, tokens, private family logs, production screenshots, or private deployment paths belong in this repository.
