# Production migration checklist

Use this when comparing an existing private child-learning deployment with the public LearnBuddy core before migrating anything back into production.

The rule is boring on purpose: audit first, migrate later. Do not copy private runtime data, bot tokens, chat IDs, chat logs, screenshots, or local profile prompts into this repository.

## 1. Read-only inventory

Record capabilities, not private values:

- parent-created exercise flow
- child answer evaluation flow
- delivery metadata semantics
- parent answer/status/report paths
- daily and weekly parent-status automation
- scheduled exercise dispatch path
- child control commands such as repeat/help/next
- backup/restore coverage
- queue policy and `queue_max`
- runtime-file write permissions and doctor output
- active gateway/timer topology

Expected output: a short gap list that says whether the public core is equivalent, ahead, or intentionally different.

## 2. Public-core readiness gate

Before using public LearnBuddy as the migration source, require:

```bash
pytest -q
python -m compileall -q src plugins tests
git diff --check
pytest --collect-only -q
learnbuddy doctor --config ./learnbuddy.yaml
learnbuddy backup --config ./learnbuddy.yaml --output ./learnbuddy-backup.zip
```

For Telegram installs, also prove the installed Hermes plugin/profile sees the relevant tool contracts. Repo-level checks are not enough when plugins are copied into a Hermes profile.

## 3. Dry-run shadow rehearsal

Use a temporary storage directory and `delivery.mode: dry_run`:

```bash
learnbuddy setup --config ./shadow-learnbuddy.yaml --data-dir ./shadow-data --child-name Learner --agent-name LearnBuddy
learnbuddy doctor --config ./shadow-learnbuddy.yaml
learnbuddy queue --config ./shadow-learnbuddy.yaml --subject math --prompt "1 + 1?" --answer "2"
learnbuddy next --config ./shadow-learnbuddy.yaml --deliver
learnbuddy answer --config ./shadow-learnbuddy.yaml "2"
learnbuddy weekly-status --config ./shadow-learnbuddy.yaml --notify --include-empty --force
```

Expected result: all delivery results are `dry_run`, no real child or parent chat is contacted, and `status.pending` is clean after the answer.

## 4. Queue safety parity

Set and test `safety.queue_max` before migration. This prevents parent/chat automation from piling up unlimited follow-up tasks while one exercise is open.

```yaml
safety:
  max_attempts: 3
  queue_max: 5
  daily_auto_limit: 1
```

When the queue is full, parent create/send paths must return `queue_full` and must not store or deliver a new child-facing exercise.

## 5. Backup and rollback gate

Before touching production:

- stop or pause competing answer watchers/timers
- create a production backup with the existing system
- create a LearnBuddy backup after any import/rehearsal
- verify restore into a fresh directory
- document the exact gateway/timer restart window
- keep the old production profile runnable until the new path has passed a real controlled smoke

## 6. Controlled cutover smoke

Only after the dry-run rehearsal is green:

1. start parent gateway with parent-only `learnbuddy_learning`
2. start child gateway with child-only `learnbuddy_child`
3. keep legacy watchers disabled if the child gateway polls the same bot
4. send one controlled exercise
5. answer it once
6. verify parent answer-status/report sees the completed answer
7. verify delivery metadata and backup/doctor are clean

Completion marker:

```text
production_migration_smoke=ok
```

Anything less is not a migration. It's just vibes with a fuse attached.
