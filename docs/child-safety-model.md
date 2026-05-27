# Child Safety Model

The child-facing profile is least-privilege by default, but it is designed to grow. LearnBuddy should let a child practice responsible AI use over time while parents remain in control.

A parent/main Hermes profile may use the broader `learnbuddy_learning` toolset for admin work. A child who talks directly to LearnBuddy should use a separate **full child-facing Hermes Agent** with its own profile, gateway, Telegram bot, capability levels, parent approval, audit, and downgrade path.

## Architecture

```text
Parent profile -> learnbuddy_learning -> parent/admin decisions
Child profile  -> learnbuddy_child + staged optional Hermes features
Child gateway  -> hermes-gateway-learnbuddy-child.service
```

The old narrow watcher remains useful as a fallback/repair worker, but it is not the long-term child-agent architecture.

## Capability levels

The default presets are the public capability levels:

- `locked` — only `learnbuddy_child`; answer current exercises, check status, request parent help.
- `guided` — `learnbuddy_child`, `tts`, `vision`; allows voice feedback and worksheet/photo understanding.
- `curious` — guided plus narrow `search`; allows supervised learning research.
- `teen-supervised` — curious plus `skills`, `delegation`, and `cronjob`; only after parent approval and review.

These levels are examples, not moral labels. The right level depends on age, maturity, trust, and the current learning goal. Parents can downgrade at any time.

## Forbidden by default

Forbidden in every shipped preset:

- terminal
- file access
- code execution
- smart home control
- generic messaging
- purchases / external actions

Broad skills, delegation, or cron access are allowed only in the `teen-supervised` preset and only for child-safe learning organization. They must not become a backdoor to files, terminals, smart-home control, or external messaging.

## Allowed bounded actions

The `learnbuddy_child` toolset currently allows:

- submit an answer for the current exercise
- check current pending status
- request parent help for learning support

The child profile should not be able to create arbitrary parent/admin tasks, inspect unrelated system state, send generic messages, or access local files.

## Parent approval and audit

Feature upgrades should be explicit:

- Parent approves the target capability level.
- Parent reviews the enabled toolsets before gateway restart.
- Parent can request a short audit summary for active level and optional toolsets.
- Parent can downgrade immediately if the level is too broad.

Use `templates/child-profile/config-snippet.yaml` as the public-safe configuration model. It includes `capability_level`, `allowed_optional_toolsets`, `parent_approval_required: true`, `audit_summary_for_parent: true`, and `forbidden_toolsets`.

## Setup

Use [`setup-child-profile.md`](setup-child-profile.md) or the helper script:

```bash
scripts/setup-child-profile.sh --profile learnbuddy-child --config ./learnbuddy.yaml --capability-level guided
```

Verify before real use:

```bash
hermes --profile learnbuddy-child plugins list
hermes --profile learnbuddy-child tools list
hermes --profile learnbuddy-child config check
```

The intended dedicated gateway service is:

```text
hermes-gateway-learnbuddy-child.service
```
