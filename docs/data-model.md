# Data Model

MVP storage is JSON/JSONL because it is easy to inspect, backup, and recover.

Runtime files:

- `exercises.jsonl` — configured/public-safe exercises.
- `sessions.jsonl` — opened exercise sessions and their source metadata.
- `answers.jsonl` — submitted answers and evaluation results.
- `state.json` — current pending exercise, queue, and child-delivery metadata.
- `help_requests.jsonl` — bounded child/parent help requests.
- `scheduled_exercises.jsonl` — parent-scheduled concrete exercises and dispatch status.
- `plans.jsonl` — learning-plan history.
- `plan-state.json` — active learning-plan pointer and plan automation state.
- `material-sets.jsonl` — parent-supplied worksheet/material review state.
- `pending-reminder-state.json` — sent 24h/48h child-reminder and 72h parent-escalation markers for the current pending session.

SQLite migration is planned once dashboard/filtering/multi-child support needs it.
