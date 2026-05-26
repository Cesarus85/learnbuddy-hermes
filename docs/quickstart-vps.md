# VPS Quickstart

VPS hosting is a first-class LearnBuddy deployment option when a family already uses cloud model providers or wants a small always-on server.

Start with a private server and synthetic data. Do not expose a child-facing endpoint until `learnbuddy doctor`, a dry-run smoke, backups, and routing checks are green.

## Baseline requirements

- Ubuntu 24.04 LTS or another maintained Linux server
- non-root SSH user with key-based login
- firewall enabled, with only SSH and required web ports open
- system packages updated before install
- secrets stored in an environment file or secret manager outside git
- backups before upgrades
- HTTPS via Caddy, nginx, or another reverse proxy when a web/API surface is enabled

## Architecture

```text
Family devices
  -> Telegram or future Web/PWA
  -> VPS running Hermes + LearnBuddy
  -> configured model provider or private model endpoint
```

## 1. Prepare an isolated user and directory

Example layout:

```text
/opt/learnbuddy/
  repo/
  .venv/
  config/
  data/
  backups/
```

Recommended ownership: a dedicated `learnbuddy` service user. Do not run child-facing services as `root`.

## 2. Install from a clean source checkout or release artifact

For alpha evaluation from a checkout:

```bash
python3 -m venv /opt/learnbuddy/.venv
. /opt/learnbuddy/.venv/bin/activate
python -m pip install -e '/opt/learnbuddy/repo[test]'
```

For a future tagged release, prefer a signed/verified release artifact over a mutable branch checkout.

## 3. Create dry-run config and storage

```bash
learnbuddy setup \
  --config /opt/learnbuddy/config/learnbuddy.yaml \
  --data-dir /opt/learnbuddy/data/runtime \
  --child-id learner \
  --child-name Learner \
  --agent-name LearnBuddy

learnbuddy doctor --config /opt/learnbuddy/config/learnbuddy.yaml
```

The generated config should keep `delivery.mode: dry_run` until routing is intentionally configured.

## 4. Run a full local smoke on the VPS

```bash
learnbuddy queue --config /opt/learnbuddy/config/learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
learnbuddy next --config /opt/learnbuddy/config/learnbuddy.yaml --deliver
learnbuddy answer --config /opt/learnbuddy/config/learnbuddy.yaml "4"
learnbuddy status --config /opt/learnbuddy/config/learnbuddy.yaml
learnbuddy report --config /opt/learnbuddy/config/learnbuddy.yaml --notify
learnbuddy backup --config /opt/learnbuddy/config/learnbuddy.yaml --output /opt/learnbuddy/backups/smoke.zip
learnbuddy restore --archive /opt/learnbuddy/backups/smoke.zip --data-dir /opt/learnbuddy/data/restore-smoke
```

Expected delivery status for the first VPS smoke: `dry_run`.

## 5. Hardening before real family use

- Keep SSH key-based and disable password login if your provider/setup allows it.
- Keep OS updates and Python dependency updates on a regular schedule.
- Store Telegram/model-provider secrets outside the repo.
- Restrict file permissions on config, runtime data, and backups.
- Use a firewall and avoid exposing LearnBuddy internals directly.
- Use HTTPS when adding an HTTP API or dashboard.
- Test restore, not only backup creation. Untested backups are decorative confetti.
- Treat backup zip files as private child learning data.

## 6. Telegram and model-provider notes

Telegram and model-provider credentials should be configured with environment variable names in YAML and real values in the process environment. `learnbuddy doctor` should show missing variable names, not secret values.

If a cloud model provider is used, family prompts and answers may be sent to that provider. Explain this clearly to parents and choose retention/privacy settings deliberately.
