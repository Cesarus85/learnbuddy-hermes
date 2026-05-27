# Telegram Command Contracts

LearnBuddy's public alpha is Telegram-first. Web/PWA/API surfaces can be added later on top of the same core operations; they are not required for the Telegram MVP.

## Parent Telegram command contracts

The parent-facing Hermes profile uses the `learnbuddy_learning` toolset. It may perform admin and delivery actions, but every pushed message must be explicit and bounded. For live parent-gateway routing, install the public SOUL/contracts into the parent profile with `scripts/setup-parent-profile.sh`; the SOUL tells the agent to read `learnbuddy_parent_command_contracts` before handling LearnBuddy Telegram commands.

### Current status

- Parent examples: `Status`, `Was ist offen?`, `Zeig die Queue`, `Hat Learner gerade eine offene Aufgabe?`
- Tool: `learnbuddy_learning_status`
- Side effect: none
- Rule: read-only; answers only current pending/queue state. Do **not** use this for recent/completed answer questions.

### Answer status

- Parent examples: `Hat Learner geantwortet?`, `Wie war die Antwort?`, `Status der beantworteten Frage`, `Kam eine Antwort an?`
- Tool: `learnbuddy_parent_answer_status`
- Side effect: none
- Rule: read-only; joins answer history with the original prompt and persisted parent-notification delivery metadata.

### Report

- Parent examples: `Bericht`, `Wie lief es heute?`, `Schick mir einen Report`
- Tool: `learnbuddy_parent_report`
- Default args: `notify=false`
- Rule: use `notify=true` only when the parent explicitly asks to send/push the report.

### Daily parent status

- Parent examples: `Tagesstatus`, `Schick den Tagesstatus`, `Status heute Abend`
- Tool: `learnbuddy_daily_parent_status`
- Default args: `notify=false`, `include_empty=false`, `force=false`
- Rule: scheduler-safe and bounded. It renders one local-day report with started tasks, latest answer per task, attempt history, and subject totals; respects `heute pausieren`/`pause_today`; skips duplicate sends for the same local date; and skips truly empty days (no started tasks and no answers) unless `include_empty=true`.
- Installable timer: `scripts/install-daily-status-timer.sh --config learnbuddy.yaml --enable --start` writes a systemd user timer whose service runs `learnbuddy daily-status --notify`.

### Parent automation control

- Parent examples: `heute pausieren`, `Lernbot heute aus`, `weiter`, `Automatik wieder an`
- Tool: `learnbuddy_parent_automation_control`
- Args: `action=status|pause_today|resume`, optional `reason`
- Rule: controls only LearnBuddy scheduled parent-facing automation. It does not create tasks, answer for the child, change system settings, or notify external humans by itself.

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
- Required args: `prompt`, plus `answer_or_expected_answers` (`answer` or ordered `expected_answers`)
- Parent examples include multi-part prompts such as `Frage Learner folgende Aufgaben`; calculate or verify the expected answers first, then pass them as ordered `expected_answers`.
- Rule: use only when the parent provides or the agent deterministically verifies a concrete child-facing prompt and expected answer(s). The tool refuses to send without an expected answer.

## Child boundary

Parent command contracts are never exposed through the `learnbuddy_child` toolset. Child Telegram handling remains narrow: answers, `Nochmal`, `Hilfe`, `Ich weiß nicht`, `Noch eine`, and `Noch eine Aufgabe` are processed by the Kids-Bot watcher without admin capability.

### Child-intent classification

The watcher uses a two-stage child-intent classifier:

1. **Preflight** — fast phrase-based lookup against known control messages (`Nochmal`, `Hilfe`, `Ich weiß nicht`, `Noch eine`, `Weiter`, `Mehr bitte`, etc.). No network call, no LLM, instant.
2. **Semantic fallback** — if the preflight misses and an LLM-backed intent classifier is configured (`intent_classifier.enabled: true` in config), the watcher asks a small model to classify free-form child text into `repeat`, `help`, `next`, or `answer` (treated as not-a-control-message). This catches natural variations like "ich will noch was rechnen", "ich checks nicht", "was war die frage nochmal" — without maintaining an ever-growing phrase list.

The semantic classifier is **opt-in** and **bounded**:

- It can only return `repeat`, `help`, or `next` — the same three intents the phrase list returns.
- It can never generate exercises, impersonate the child, or trigger admin actions.
- If the LLM call fails or times out, the message falls through to regular answer evaluation — never silently ignored.
- The API key is read from an environment variable (`LEARNBUDDY_INTENT_API_KEY` by default); never stored in config files.

### Child `Noch eine`

- With a pending task: the watcher replies that the learner should finish the current task first; attempts stay unchanged.
- Without a pending task: the watcher may open and deliver exactly one automatic exercise through the scheduler-safe policy path.
- Policy gates: `allowed_hours`, `daily_auto_limit`, no current pending session, and existing configured exercises only.
- Rejections are child-friendly (`daily_limit_reached`, `outside_allowed_hours`, or `no_matching_exercise`) and never trigger free-form LLM task generation. If the child asked for another task and LearnBuddy cannot open one, the watcher records a bounded parent-help request and notifies parents when parent notifications are enabled.

## Safety rules

- No unbounded exercise generation from vague parent text.
- Delivery-state remains authoritative: pending alone does not prove that the child saw the prompt.
- Parent-triggered pushed reports require explicit parent intent; child-answer/result notifications may be automatic when the child profile is configured to notify parents.
- Missing Telegram configuration must report variable names only, never secret values.
