# Telegram Command Contracts

LearnBuddy's public alpha is Telegram-first. Web/PWA/API surfaces can be added later on top of the same core operations; they are not required for the Telegram MVP.

## Parent Telegram command contracts

The parent-facing Hermes profile uses the `learnbuddy_learning` toolset. It may perform admin and delivery actions, but every pushed message must be explicit and bounded.

### Status

- Parent examples: `Status`, `Was ist offen?`, `Zeig die Queue`, `Hat Learner gerade eine Aufgabe?`
- Tool: `learnbuddy_learning_status`
- Side effect: none
- Rule: read-only; never sends Telegram messages.

### Report

- Parent examples: `Bericht`, `Wie lief es heute?`, `Schick mir einen Report`
- Tool: `learnbuddy_parent_report`
- Default args: `notify=false`
- Rule: use `notify=true` only when the parent explicitly asks to send/push the report.

### Resend pending prompt

- Parent examples: `Nochmal senden`, `Learner hat die Aufgabe nicht bekommen`, `Schick die offene Aufgabe erneut`
- Tool: `learnbuddy_deliver_pending_exercise`
- Args: `force=true`
- Rule: resend only the existing pending prompt. Do not create a new exercise and do not answer for the child.

### Dispatch one scheduled plan item

- Parent examples: `Starte den Lernplan`, `Schick eine geplante Aufgabe`, `Heute eine Mathe-Aufgabe aus dem Plan`
- Tool: `learnbuddy_dispatch_plan`
- Rule: policy-bounded. The command respects `allowed_hours`, `daily_auto_limit`, and existing pending sessions.

### Create and send one concrete exercise

- Parent examples: `Schick Learner: Was ist 100 + 101?`, `Gib Learner eine Matheaufgabe mit Antwort 201`
- Tool: `learnbuddy_create_and_send_exercise`
- Required args: `prompt`, `answer`
- Rule: use only when the parent provides or approves a concrete child-facing prompt and expected answer.

## Child boundary

Parent command contracts are never exposed through the `learnbuddy_child` toolset. Child Telegram handling remains narrow: answers, `Nochmal`, `Hilfe`, and `Ich weiß nicht` are processed by the Kids-Bot watcher without admin capability.

## Safety rules

- No unbounded exercise generation from vague parent text.
- Delivery-state remains authoritative: pending alone does not prove that the child saw the prompt.
- Parent notifications require explicit parent intent.
- Missing Telegram configuration must report variable names only, never secret values.
