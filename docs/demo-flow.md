# Demo Flow

This is a complete public-alpha smoke path using synthetic data only. It is safe to run locally because delivery stays in `dry_run` mode.

## Goal

Prove the full lifecycle:

```text
setup -> doctor -> queue -> next --deliver -> deliver-pending -> answer -> status -> report --notify -> backup -> restore
```

No Telegram token, chat ID, production child data, or private deployment path is needed.

## 1. Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

## 2. Create config and storage

```bash
learnbuddy setup \
  --config ./learnbuddy.yaml \
  --data-dir ./data/learnbuddy \
  --child-id learner \
  --child-name Learner \
  --agent-name LearnBuddy
```

The generated YAML should contain:

```yaml
delivery.mode: dry_run
```

This means `--deliver` and `--notify` return dry-run delivery results instead of sending network messages.

## 3. Validate environment

```bash
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy doctor --config ./learnbuddy.yaml --format json
```

Expected result: overall status is ok, storage is usable or creatable, and delivery is dry-run.

## 4. Queue a synthetic fixture exercise

The fixture file is:

```text
examples/exercises/de/grade-5-mixed.jsonl
```

Manual queue example:

```bash
learnbuddy queue \
  --config ./learnbuddy.yaml \
  --subject math \
  --prompt "Berechne: 7 × 8." \
  --answer "56"
```

The command returns JSON with an exercise id.

## 5. Open, dry-run deliver, and repair-send if needed

This is the `learnbuddy next --deliver` step of the demo lifecycle. `deliver-pending` is the explicit repair path for the "pending but the learner never saw it" case; in dry-run it should report `already_sent` after a successful `next --deliver`.

```bash
learnbuddy next --config ./learnbuddy.yaml --deliver
learnbuddy deliver-pending --config ./learnbuddy.yaml
```

Expected result: one pending exercise opens, the delivery result has `status` set to `dry_run`, and the pending session records child-delivery metadata.

## 6. Submit an answer

```bash
learnbuddy answer --config ./learnbuddy.yaml "56"
```

Expected result: `correct` is true and the pending exercise is completed.

## 7. Check status and parent report

This covers the `learnbuddy report --notify` parent-notification step.

```bash
learnbuddy status --config ./learnbuddy.yaml
learnbuddy report --config ./learnbuddy.yaml --notify
```

Expected parent notification result: `dry_run` unless Telegram parent delivery is intentionally configured.

## 8. Backup and restore

This covers `learnbuddy backup` and `learnbuddy restore`.

```bash
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
```

Restore refuses to overwrite existing data unless `--force` is passed.

## 9. Run tests

```bash
pytest -q
```

## Public-safety rules for demos

- Use only synthetic names like `Learner`, `Emma`, or `Lumi`.
- Do not paste real answers, chat exports, screenshots, tokens, or chat IDs into examples.
- Keep demo delivery in `dry_run` mode unless using a dedicated staging bot.
- Treat backup files as private learning data once they contain real family content.
