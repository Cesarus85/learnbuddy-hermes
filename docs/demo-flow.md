# Demo Flow

This is a complete public-alpha smoke path using synthetic data only. It is safe to run locally because delivery stays in `dry_run` mode.

## Goal

Prove the full lifecycle:

```text
setup -> seed -> doctor -> queue -> schedule-exercise -> material add-text -> material approve -> plan create -> dispatch-plan -> next --deliver -> deliver-pending -> answer -> status -> weekly-status --notify -> report --notify -> backup -> restore
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
learnbuddy seed --config ./learnbuddy.yaml --pack de/bavaria-realschule-grade-5
```

The seed command imports the bundled public-safe Bavaria/Realschule grade-5 pack: 80 synthetic Mathe/Deutsch/Englisch tasks with topic metadata. It is idempotent, so reruns skip existing exercise IDs. With default paths the short form is `learnbuddy seed --pack de/bavaria-realschule-grade-5`.

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

## 4. Seed or queue synthetic exercises

The realistic public-safe starter pack is bundled in the package and can be imported directly:

```bash
learnbuddy seed --config ./learnbuddy.yaml --pack de/bavaria-realschule-grade-5
```

It imports 80 synthetic Bavaria/Realschule grade-5 exercises across Mathe, Deutsch, and Englisch. The tiny fixture file is still useful for smoke tests:

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

## 5. Material review, schedule/open, dry-run deliver, and repair-send if needed

This is the material/scheduled/plan/automatic dispatch part of the demo lifecycle. `learnbuddy material add-text` stores parent-supplied worksheet or copied material candidates in `material-sets.jsonl`; `learnbuddy material approve` converts selected candidates into bounded exercises only after ordered expected answers are provided. `learnbuddy schedule-exercise` records a parent-created timed exercise for later; it does not prove the learner saw anything. `learnbuddy plan create` stores bounded parent-approved plan state over existing exercises. `dispatch-plan` is the delivery dispatcher: it opens and delivers one due scheduled, active-plan, or automatic exercise only when policy allows it (`allowed_hours`, no current pending item). Active plans record `source=learning_plan` and `plan_id`; `daily_goal` gates plan-dispatched items. `daily_auto_limit` gates generic automatic exercise selection; explicit parent-scheduled due exercises wait behind pending work, then dispatch even if the automatic daily limit is already used. `deliver-pending` is the explicit repair path for the "pending but the learner never saw it" case; in dry-run it should report `already_sent` after a successful delivery.

```bash
learnbuddy schedule-exercise \
  --config ./learnbuddy.yaml \
  --subject math \
  --prompt "Berechne: 8 + 9." \
  --answer "17" \
  --due-at "2099-01-01T10:30:00+01:00"
learnbuddy material add-text --config ./learnbuddy.yaml --title "Arbeitsblatt 1" --subject math --text "10 + 5?" --candidate "10 + 5?"
MATERIAL_ID=$(learnbuddy material status --config ./learnbuddy.yaml | python -c 'import json,sys; print(json.load(sys.stdin)["material_sets"][-1]["id"])')
learnbuddy material approve --config ./learnbuddy.yaml --material-id "$MATERIAL_ID" --expected-answer "15"
learnbuddy plan create --config ./learnbuddy.yaml --title "Mathe-Woche" --subject math --daily-goal 1
learnbuddy dispatch-plan --config ./learnbuddy.yaml
learnbuddy deliver-pending --config ./learnbuddy.yaml
learnbuddy plan status --config ./learnbuddy.yaml
# Manual parent-open path still exists: learnbuddy next --deliver
# learnbuddy next --config ./learnbuddy.yaml --deliver
```

Expected result: one pending automatic exercise opens during allowed hours, the delivery result has `status` set to `dry_run`, and the pending session records child-delivery metadata.

## 6. Submit an answer

```bash
learnbuddy answer --config ./learnbuddy.yaml "56"
```

Expected result: `correct` is true and the pending exercise is completed.

## 7. Check status and parent reports

This covers the weekly parent-status automation and the manual `learnbuddy report --notify` parent-notification step. Weekly status is scheduler-safe: it respects pause-today, once-per-week, and empty-week guards.

```bash
learnbuddy status --config ./learnbuddy.yaml
learnbuddy weekly-status --notify --config ./learnbuddy.yaml
learnbuddy report --config ./learnbuddy.yaml --notify
```

Expected parent notification result: `dry_run` unless Telegram parent delivery is intentionally configured.

## 8. Backup and restore

This covers `learnbuddy backup` and `learnbuddy restore`.

```bash
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
learnbuddy restore --archive ./learnbuddy-backup.zip --data-dir ./restored-learnbuddy-data
```

Restore refuses to overwrite existing data unless `--force` is passed. Backups include scheduled exercises and `material-sets.jsonl`, so parent-timed tasks and reviewed worksheet/material queues survive restore instead of quietly vanishing like cowards.

## 9. Run tests

```bash
pytest -q
```

## Public-safety rules for demos

- Use only synthetic names like `Learner`, `Emma`, or `Lumi`.
- Do not paste real answers, chat exports, screenshots, tokens, or chat IDs into examples.
- Keep demo delivery in `dry_run` mode unless using a dedicated staging bot.
- Treat backup files as private learning data once they contain real family content.
