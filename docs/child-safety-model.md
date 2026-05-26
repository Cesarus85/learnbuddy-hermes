# Child Safety Model

The child-facing profile is least-privilege by default.

A parent/main Hermes profile may use the broader `learnbuddy_learning` toolset for admin work. A child who talks directly to LearnBuddy should use a separate profile with only the narrow `learnbuddy_child` toolset.

## Forbidden by default

- terminal
- file access
- code execution
- smart home control
- generic messaging
- purchases / external actions
- broad skills, delegation, or cron access unless a separate child-safety design has been reviewed

## Allowed bounded actions

The `learnbuddy_child` toolset currently allows:

- submit an answer for the current exercise
- check current pending status
- request parent help for learning support

The child profile should not be able to create arbitrary parent/admin tasks, inspect unrelated system state, send generic messages, or access local files.

## Setup

Use [`setup-child-profile.md`](setup-child-profile.md) or the helper script:

```bash
scripts/setup-child-profile.sh --profile learnbuddy-child --config ./learnbuddy.yaml
```

Verify before real use:

```bash
hermes --profile learnbuddy-child plugins list
hermes --profile learnbuddy-child tools list
hermes --profile learnbuddy-child config check
```
