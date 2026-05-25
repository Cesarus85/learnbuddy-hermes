# LearnBuddy Hermes

Self-hosted, parent-controlled learning buddy for families, built as a Hermes Agent extension pack.

> Status: early scaffold. Do not use this for real children yet.

## What this is

LearnBuddy is a safe, bounded learning companion that can:

- send short exercises to a child
- evaluate answers kindly
- limit attempts and explain when attempts are used up
- track learning progress locally
- send parent-facing summaries
- run via Telegram first, then Web/PWA and later iOS

## What this is not

- not a replacement for parents, teachers, school, tutoring, or professional advice
- not a hosted child-AI SaaS
- not a general-purpose child chatbot with full system access
- not connected to ads, tracking, or analytics

## Deployment modes

Supported design targets:

1. Homehosting: Raspberry Pi, mini-PC, NAS, Mac mini, local server.
2. VPS + cloud LLM: useful when a family already uses OpenAI/OpenRouter/Gemini/etc.
3. Local LearnBuddy + cloud LLM: child data and orchestration local, model calls in the cloud.
4. Advanced: VPS LearnBuddy connected to a private/local model endpoint via VPN/Tailscale.

## Current roadmap

- `0.1`: Telegram self-hosted MVP
- `0.2`: VPS/cloud-LLM setup docs and hardening
- `0.3`: Parent dashboard / PWA
- `0.4`: multiple children and parent devices
- `0.5`: iOS companion app

## Safety baseline

The child-facing Hermes profile must not have dangerous generic tools enabled. Default forbidden toolsets:

- terminal
- file
- code execution
- smart home / Home Assistant
- generic messaging
- purchases or external actions

Only bounded LearnBuddy tools should be exposed to the child profile.

## Repository layout

```text
plugins/learnbuddy-learning/   Hermes plugin wrapper
src/learnbuddy_core/           shared core logic
scripts/learnbuddy             local CLI entry point
templates/                     profile/config templates
examples/                      safe example configs
docs/                          setup, safety, privacy, roadmap
tests/                         regression tests
```

## Quick start

Not ready yet. Planned target:

```bash
learnbuddy setup
learnbuddy doctor
```

Until then, treat this repository as a scaffold.

## Privacy promise for the project

No real child data, chat IDs, tokens, private family logs, or production screenshots belong in this repository.
