# LearnBuddy Extraction Roadmap

This document tracks the public-safe extraction from a working private child-learning setup into a generic LearnBuddy package.

No private child data, chat IDs, raw answers, parent names, or production credentials belong in this repository. Production paths and family-specific details stay in private operational notes only.

## Extraction principles

- Build generic modules first; do not copy production files wholesale.
- Treat the production setup as a behavior reference, not as source material to publish.
- Keep child identity, parent contacts, delivery channels, provider choices, schedules, and data paths configurable.
- Use tests and fixtures with neutral names and synthetic data.
- Run a privacy/secret scan before every public-facing milestone.

## Telegram-first alpha scope

The public 0.1 alpha is Telegram-first. The critical path is:

1. local dry-run CLI lifecycle
2. Docker Compose dry-run bootstrap and smoke path
3. parent/admin Hermes tool contracts
4. child Telegram delivery and answer watching
5. parent Telegram reporting/help notifications
6. controlled E2E smoke tests with synthetic state and no required live child/parent messages

Dashboard, Web/PWA, generic API, and iOS stay out of the 0.1 alpha critical path. They are later surfaces over the same bounded operations once Telegram delivery, pending-state repair, child controls, and parent command contracts are boringly reliable.

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
| Parent-help escalation | Public-safe help-request store plus optional parent notification |
| Daily learning status | Report renderer independent from transport |
| Scheduled plan dispatcher | Scheduler-friendly plan dispatch service |
| Dashboard intent mailbox | Optional web/dashboard integration layer |
| Backups and restore | CLI commands and documented data layout |
| Doctor checks | `learnbuddy doctor` environment and safety validator |

## Proposed public configuration surface

A minimal single-child setup should be expressible without code edits:

```yaml
child:
  id: "learner"
  display_name: "Learner"
  grade: "5"
  school_context: "generic"
  subjects:
    - math
    - german
    - english
agent:
  name: "LearnBuddy"

safety:
  max_attempts: 3
  queue_max: 5
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
  mode: "telegram"
  child:
    type: "telegram"
    bot_token_env: "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN"
    allowed_chat_ids_env: "LEARNBUDDY_ALLOWED_CHILD_CHAT_ID"
  telegram:
    child_bot_env: "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN"
    allowed_child_chat_id_env: "LEARNBUDDY_ALLOWED_CHILD_CHAT_ID"
  parents:
    - type: "telegram"
      bot_token_env: "LEARNBUDDY_PARENT_TELEGRAM_BOT_TOKEN"
      target_env: "LEARNBUDDY_ALLOWED_PARENT_CHAT_ID"
```

## First extraction milestone

P0 should be deliberately boring:

- [x] Load synthetic exercise fixtures.
- [x] Open one manual exercise.
- [x] Submit wrong answers until the attempt limit is exhausted.
- [x] Submit a correct answer for another exercise.
- [x] Queue a second exercise while one is pending.
- [x] Render a daily parent report from synthetic sessions/answers.
- [x] Run without production `HERMES_HOME`.

Implemented in the first public runtime slice:

- `learnbuddy_core.runtime.LearnBuddyRuntime`
- plugin wrapper tools in `plugins/learnbuddy-learning/__init__.py`
- synthetic tests in `tests/test_runtime.py` and `tests/test_plugin_wrapper.py`

Phase 3 doctor/CLI slice adds:

- `learnbuddy_core.doctor.build_doctor_report(...)`
- text and JSON `learnbuddy doctor` output
- storage and delivery environment checks that report env-var names only, not values
- JSON runtime commands: `learnbuddy queue`, `seed`, `next`, `dispatch-plan`, `deliver-pending`, `answer`, `status`, `help-request`, `watch-telegram-answers`, and `report`
- curriculum/content parity seed: `learnbuddy seed --pack de/bavaria-realschule-grade-5` imports 80 public-safe synthetic Bavaria/Realschule grade-5 exercises across Mathe, Deutsch, and Englisch, without copying private production data
- scheduled plan dispatcher parity: `dispatch-plan` respects `daily_auto_limit`, `allowed_hours`, and existing pending work before opening/delivering one automatic exercise
- delivery-state parity: pending sessions record child delivery status/message metadata; the watcher and `deliver-pending` repair undelivered pending prompts before expecting child answers
- Hermes plugin role split: broad parent/admin `learnbuddy_learning` toolset plus narrow child-facing `learnbuddy_child` aliases
- public-safe `learnbuddy setup` that creates a starter config and local storage without secrets
- zip-based `learnbuddy backup` and `learnbuddy restore` for runtime data files only

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
- private workstation/server operational secrets
