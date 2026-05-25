# VPS Quickstart

Status: planned.

VPS hosting is a first-class deployment option when a family already uses cloud LLMs.

Baseline requirements:

- Ubuntu 24.04 or similar
- non-root SSH user
- firewall enabled
- HTTPS via Caddy or equivalent for web/app mode
- secrets in `.env`, never in git
- backups before upgrades

Architecture:

```text
Family devices -> Telegram/Web/iOS -> VPS Hermes + LearnBuddy -> Cloud LLM API
```
