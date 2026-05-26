# Privacy Notes

This page expands the root [`../PRIVACY.md`](../PRIVACY.md) policy for implementation and documentation work.

## Defaults

- No telemetry in the MVP.
- No ads.
- No third-party analytics for child mode.
- Keep examples synthetic.
- Delivery defaults to `dry_run` for setup and demos.
- Do not print secret values in `doctor`, errors, logs, or test fixtures.

## Runtime data

The local runtime currently uses JSON/JSONL files for:

- queued exercises
- pending/completed state
- submitted answers
- attempt/session history

These files are acceptable for alpha because they are easy to inspect and backup. They are also private family data once real content is used.

## Backups

Backup archives contain runtime learning data. Treat them like private documents:

- keep them outside git
- restrict file permissions
- test restore regularly
- delete stale copies intentionally

## Public examples

Public fixtures must use:

- neutral names
- simple synthetic prompts
- no local deployment paths
- no screenshots
- no IDs copied from real messaging systems
- no child-specific private context

## Cloud and VPS disclosures

Docs must clearly say when a deployment sends prompts/answers to a model provider or stores data on a VPS. Self-hosted does not automatically mean local-only; the selected provider and deployment mode matter.
