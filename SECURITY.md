# Security Policy

LearnBuddy is child-facing software. Treat security bugs as serious even when they look small.

## Supported versions

| Version | Support status |
| --- | --- |
| `0.1.0-alpha` | Security fixes accepted during alpha preparation |
| earlier commits | Best-effort only |

## Reporting a vulnerability

Use GitHub private vulnerability reporting when available, or contact the maintainers through the private channel listed by the repository owner.

Do not publish exploit details involving child data, auth tokens, profile isolation bypasses, message routing bugs, backup disclosure, or prompt-injection paths before a fix exists.

Please include:

- affected version or commit
- deployment mode: local, Telegram, VPS, or other
- impact summary
- minimal reproduction using synthetic data
- whether any real child data or credentials may have been exposed

Never include real child records, chat exports, tokens, or screenshots with identifying metadata in a public issue.

## Security principles

- Child profiles are least-privilege by default.
- No shell, file, code execution, smart-home, purchasing, or generic messaging tools in child profiles by default.
- Parent/admin actions are separated from child-facing actions.
- Delivery adapters must avoid leaking token values or chat identifiers in errors.
- Local-first data storage is the default.
- No secrets in git, examples, tests, or docs.
- No production child data in fixtures.
- Backups are private learning data once used with real families.
- Fail closed when routing, recipient, or credential checks are ambiguous.

## Scope for alpha review

In scope:

- LearnBuddy core runtime and evaluator behavior
- CLI setup, doctor, queue, answer, report, backup, and restore
- Telegram delivery adapter boundaries
- profile/toolset safety guidance
- docs/examples that could accidentally leak secrets or private data

Out of scope for the initial alpha:

- hosted SaaS security claims
- school-wide deployment management
- app-store/iOS hardening
- dashboard authorization for a future web UI

## Maintainer response goal

For high-impact reports involving child data exposure, credential leakage, or child-to-parent routing mistakes, aim to acknowledge within 72 hours once the project is public. Lower-impact hardening suggestions may be handled in normal issue triage.
