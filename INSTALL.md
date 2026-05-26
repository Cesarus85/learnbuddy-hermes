# Install LearnBuddy Hermes

This guide is written for a technical parent or an operator running a fresh local Linux/VPS setup. It covers both pieces:

1. Install and configure Hermes Agent.
2. Install LearnBuddy from this repository and run the safe dry-run lifecycle.

The default path sends nothing to Telegram and uses no child production data. Keep `delivery.mode: dry_run` until the local smoke test is green.

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

For a tagged release after alpha publication:

```bash
git checkout v0.1.0-alpha
```

## 3. Create an isolated Python environment

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

## 4. Create public-safe local config

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

## 5. Run the full dry-run smoke test

This step covers `learnbuddy next --deliver` and `learnbuddy report --notify` in the full smoke path.

```bash
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy queue --config ./learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy answer --config ./learnbuddy.yaml "4"
learnbuddy status --config ./learnbuddy.yaml
learnbuddy report --config ./learnbuddy.yaml --notify
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
```

Expected first-run behavior:

- `doctor` is ok.
- child delivery result is `dry_run`.
- parent notification result is `dry_run`.
- restore succeeds into a fresh directory.

A fuller walkthrough lives in [`docs/demo-flow.md`](docs/demo-flow.md).

## 6. Optional: use the synthetic exercise fixture

Public demo exercises live here:

```text
examples/exercises/de/grade-5-mixed.jsonl
```

They are intentionally synthetic and cover math, German, and English. They are examples, not a curriculum.

## 7. Optional: install the Hermes plugin wrapper locally

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

For unattended gateway use, set defaults in the profile environment instead of relying on the model to pass paths on every tool call:

```text
LEARNBUDDY_CONFIG_PATH=/absolute/path/to/learnbuddy.yaml
LEARNBUDDY_ENV_FILE=/absolute/path/to/learnbuddy.env
```

`LEARNBUDDY_ENV_FILE` is optional and should be mode `600`; it can hold the Telegram variables named by the YAML. Existing process environment values win over the file. The plugin also exposes `learnbuddy_create_and_send_exercise` as a one-call parent orchestration helper: create exercise → open it → deliver to the child adapter.

A child-facing profile should be created separately and locked down. Do not clone a parent/admin profile wholesale.

Example shape:

```bash
hermes profile create learnbuddy-child --no-skills --no-alias
hermes --profile learnbuddy-child config set model.provider your-provider
hermes --profile learnbuddy-child config set model.default your-model
hermes --profile learnbuddy-child plugins enable learnbuddy-learning || true
hermes --profile learnbuddy-child config check
```

Before any real child uses it, verify the child profile has no terminal, file, code execution, smart-home, purchasing, or generic messaging tools enabled. Only bounded LearnBuddy tools should be available.

## 8. Optional: Telegram delivery

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
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy report --config ./learnbuddy.yaml --notify
```

`doctor` reports missing variable names, not secret values.

## 9. VPS notes

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
