# LearnBuddy Extraction Roadmap

This document tracks the public-safe extraction from a working private child-learning setup into a generic LearnBuddy package.

No private child data, chat IDs, raw answers, parent names, or production credentials belong in this repository. Production paths and family-specific details stay in private operational notes only.

## Extraction principles

- Build generic modules first; do not copy production files wholesale.
- Treat the production setup as a behavior reference, not as source material to publish.
- Keep child identity, parent contacts, delivery channels, provider choices, schedules, and data paths configurable.
- Use tests and fixtures with neutral names and synthetic data.
- Run a privacy/secret scan before every public-facing milestone.

## Production behavior areas to extract

| Production behavior | Generic LearnBuddy target |
| --- | --- |
| Exercise pool and subject metadata | `learnbuddy_core.exercises` plus import/export fixtures |
| Answer evaluation | `learnbuddy_core.evaluator` |
| Pending session and queue state | `learnbuddy_core.state` |
| Attempt limits and final exhausted state | `learnbuddy_core.attempts` |
| Manual parent-created exercises | `learnbuddy_core.parent_queue` |
| Child delivery over Telegram | Delivery adapter interface plus Telegram adapter |
| Parent notifications | Parent notifier interface plus configurable adapters |
| Daily learning status | Report renderer independent from transport |
| Scheduled plan dispatcher | Scheduler-friendly plan dispatch service |
| Dashboard intent mailbox | Optional web/dashboard integration layer |
| Backups and restore | CLI commands and documented data layout |
| Doctor checks | `learnbuddy doctor` environment and safety validator |

## Proposed public configuration surface

A minimal single-child setup should be expressible without code edits:

```yaml
child:
  display_name: "Learner"
  grade: "5"
  school_context: "generic"
  subjects:
    - math
    - german
    - english

safety:
  max_attempts: 3
  daily_auto_limit: 1
  allowed_hours:
    from: "07:00"
    to: "21:00"
    timezone: "Europe/Berlin"

storage:
  data_dir: "${HERMES_HOME}/family/learnbuddy"

models:
  chat:
    provider: "configured-in-hermes"
    model: "configured-in-hermes"
  vision:
    provider: "optional"
    model: "optional"
  escalation:
    provider: "optional"
    model: "optional"

delivery:
  child:
    type: "telegram"
    bot_token_env: "LEARNBUDDY_TELEGRAM_BOT_TOKEN"
    allowed_chat_ids_env: "LEARNBUDDY_TELEGRAM_ALLOWED_CHATS"
  parents:
    - type: "telegram"
      target_env: "LEARNBUDDY_PARENT_TELEGRAM_CHAT"
```

## First extraction milestone

P0 should be deliberately boring:

- Load synthetic exercise fixtures.
- Open one manual exercise.
- Submit wrong answers until the attempt limit is exhausted.
- Submit a correct answer for another exercise.
- Queue a second exercise while one is pending.
- Render a daily parent report from synthetic sessions/answers.
- Run without production `HERMES_HOME`.

If this cannot run against synthetic data, it is not ready to touch real family workflows. Tiny hammer, big nail.

## Non-public material

Keep these out of the repository:

- real child names and chat IDs
- real parent names/contact IDs
- raw learning answers
- production JSONL history
- production Telegram message IDs
- production `.env` files or token-bearing config
- private Obsidian links
- private operational secrets
