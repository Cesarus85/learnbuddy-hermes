# Docker Compose quickstart

This is the shortest safe path for trying LearnBuddy without installing a local Python environment first.

The Compose path stays public-safe by default:

- `delivery.mode: dry_run`
- no Telegram token is required
- no Telegram message is sent
- runtime files stay under `learnbuddy-docker/`, which is ignored by git

## 1. Build and bootstrap the dry-run config

From the repository root:

```bash
docker compose up --build learnbuddy
```

On first start, the container creates:

```text
learnbuddy-docker/config/learnbuddy.yaml
learnbuddy-docker/data/
learnbuddy-docker/backups/
```

Expected result: `LearnBuddy doctor` reports `overall: ok` and the generated config keeps `delivery.mode: dry_run`.

## 2. Run the controlled smoke path

```bash
docker compose --profile smoke up --build --abort-on-container-exit learnbuddy-smoke
```

The smoke uses isolated temporary runtime state inside the container, writes only a demo backup into `learnbuddy-docker/backups`, and prints:

```text
delivery.mode=dry_run
compose_smoke=ok
```

The smoke covers setup, doctor, queue, open-and-deliver, answer evaluation, parent report dry-run notification, backup, and restore. No Telegram message is sent.

## 3. Use the CLI through Compose

Examples:

```bash
docker compose run --rm learnbuddy status --config /app/config/learnbuddy.yaml
docker compose run --rm learnbuddy queue --config /app/config/learnbuddy.yaml --subject math --prompt "2 + 2?" --answer "4"
docker compose run --rm learnbuddy next --config /app/config/learnbuddy.yaml --deliver
docker compose run --rm learnbuddy answer --config /app/config/learnbuddy.yaml "4"
docker compose run --rm learnbuddy backup --config /app/config/learnbuddy.yaml --output /app/backups/learnbuddy-backup.zip
```

The container entrypoint creates the config if it is missing, then forwards arguments to `learnbuddy`.

## 4. Persistent paths

Host path | Container path | Purpose
--- | --- | ---
`learnbuddy-docker/config` | `/app/config` | local config, including `learnbuddy.yaml`
`learnbuddy-docker/data` | `/app/data` | JSON/JSONL runtime state
`learnbuddy-docker/backups` | `/app/backups` | backup zip output

Do not commit anything under `learnbuddy-docker/`; it may contain family runtime data once you stop using synthetic examples.

## 5. Telegram later, deliberately

Compose does not enable Telegram by itself. To use real delivery, first complete the dry-run smoke, then edit the local config and provide the environment variables named by your config through your own process manager or Compose override file.

Keep real tokens, chat IDs, and provider keys out of the repository. Use `.env` or an untracked override file, and keep those files private.
