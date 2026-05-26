# LearnBuddy Hermes

Self-hosted, parent-controlled learning buddy for families, built as a Hermes Agent extension pack.

> Status: early scaffold. Do not use this for real children yet.

## What this is

LearnBuddy is a safe, bounded learning companion that can:

- send short exercises to a child
- evaluate answers kindly
- limit attempts and explain when attempts are used up
- track learning progress locally
- send parent-facing summaries
- run via Telegram first, then Web/PWA and later iOS

## What this is not

- not a replacement for parents, teachers, school, tutoring, or professional advice
- not a hosted child-AI SaaS
- not a general-purpose child chatbot with full system access
- not connected to ads, tracking, or analytics

## Deployment modes

Supported design targets:

1. Homehosting: Raspberry Pi, mini-PC, NAS, Mac mini, local server.
2. VPS + cloud LLM: useful when a family already uses OpenAI/OpenRouter/Gemini/etc.
3. Local LearnBuddy + cloud LLM: child data and orchestration local, model calls in the cloud.
4. Advanced: VPS LearnBuddy connected to a private/local model endpoint via VPN/Tailscale.

## Current roadmap

- `0.1`: Telegram self-hosted MVP
- `0.2`: VPS/cloud-LLM setup docs and hardening
- `0.3`: Parent dashboard / PWA
- `0.4`: multiple children and parent devices
- `0.5`: iOS companion app

See [`docs/extraction-roadmap.md`](docs/extraction-roadmap.md) for the public-safe extraction plan from private reference behavior into generic LearnBuddy modules.

## Safety baseline

The child-facing Hermes profile must not have dangerous generic tools enabled. Default forbidden toolsets:

- terminal
- file
- code execution
- smart home / Home Assistant
- generic messaging
- purchases or external actions

Only bounded LearnBuddy tools should be exposed to the child profile.

## Repository layout

```text
plugins/learnbuddy-learning/   Hermes plugin wrapper
src/learnbuddy_core/           shared core logic
scripts/learnbuddy             local CLI entry point
templates/                     profile/config templates
examples/                      safe example configs
docs/                          setup, safety, privacy, roadmap
tests/                         regression tests
```

## Quick start

Not ready yet. Current pre-alpha smoke test:

```bash
python -m pip install -e '.[test]'
learnbuddy setup --config ./learnbuddy.yaml --data-dir ./data/learnbuddy --child-id learner --child-name Learner --agent-name LearnBuddy
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy doctor --config ./learnbuddy.yaml --format json
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy status --config ./learnbuddy.yaml
learnbuddy report --config ./learnbuddy.yaml --notify
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
pytest -q
```

`learnbuddy setup` creates a starter `learnbuddy.yaml` plus the local storage directory. It is deliberately public-safe: it writes dry-run delivery by default and does not create or print Telegram tokens, chat IDs, Hermes credentials, or child production data. Use `--force` only when you intentionally want to overwrite the config file.

`learnbuddy doctor` validates the public config, storage path, and delivery environment without printing secret values. Telegram mode reports missing env-var names; `dry_run` mode stays network-free for setup checks. Runtime CLI commands (`queue`, `next`, `answer`, `status`, `report`) return JSON and use the same local state machine as the plugin wrapper. `backup` and `restore` move only the local runtime data files (`state.json`, `exercises.jsonl`, `sessions.jsonl`, `answers.jsonl`) in a zip archive and refuse to overwrite existing restored data unless `--force` is passed.

The public config surface already supports neutral child/agent identity and a transport adapter boundary:

```yaml
child:
  id: emma
  display_name: Emma
agent:
  name: Lumi
safety:
  max_attempts: 3
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

`learnbuddy_next_exercise(..., deliver=True)` can deliver the opened prompt through the configured child adapter. `learnbuddy_parent_report(..., notify=True)` can send the rendered parent report through the configured parent adapter. Use `delivery.mode: dry_run` for setup checks without network I/O.

Until the setup wizard lands, treat this repository as a scaffold.

## Privacy promise for the project

No real child data, chat IDs, tokens, private family logs, or production screenshots belong in this repository.
