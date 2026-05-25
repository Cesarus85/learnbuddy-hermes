# Security Policy

LearnBuddy is child-facing software. Treat security bugs as serious even when they look small.

## Supported versions

No stable supported version yet. This repository is pre-alpha.

## Reporting a vulnerability

Open a private security advisory on GitHub once the repository is public, or contact the maintainer privately.

Do not publish exploit details involving child data, auth tokens, profile isolation bypasses, or message routing bugs before a fix exists.

## Security principles

- Child profiles must be least-privilege.
- No shell/file/code execution tools in child profiles by default.
- No generic messaging in child profiles by default.
- Parent confirmation for sensitive changes.
- Local-first data storage.
- No secrets in git.
- No production child data in fixtures.
