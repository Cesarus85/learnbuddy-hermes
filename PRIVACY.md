# Privacy

LearnBuddy is designed as self-hosted software. Project maintainers do not receive family learning data by default.

## Privacy model

Default alpha operation is local and explicit:

- runtime data is stored on the family's chosen machine
- delivery can run in `dry_run` mode without network messages
- examples and tests use synthetic data
- telemetry, ads, and third-party analytics are not part of the MVP
- credentials are supplied by the operator, not bundled with the project

## Data a local installation may store

Depending on configuration, a LearnBuddy installation may store:

- child display name or nickname
- grade or learning-context settings
- exercise prompts and expected answers
- submitted answers
- attempt counts
- pending/completed exercise state
- parent notification preferences
- delivery status metadata
- learning plan or subject settings
- backup archives of the runtime files

These files become private family data once real content is entered.

## Data minimization

- Do not store raw chat logs as the default product view.
- Prefer learning aggregates and actionable summaries over lists of mistakes.
- Keep examples synthetic.
- Avoid unnecessary identifiers in exercises and reports.
- Use neutral child names in public docs.
- Keep backups local unless the family deliberately moves them.

## Cloud model providers

If a family configures a cloud model provider, prompts, answers, and context sent to that provider may be processed or retained under that provider's terms. Families should:

- read the provider's privacy and retention settings
- avoid sending sensitive unrelated personal information
- use local/private models when stronger data control is required
- document which provider is used for their own household

## VPS hosting

If LearnBuddy runs on a VPS, learning data is stored on rented infrastructure. Families should consider:

- provider jurisdiction and terms
- disk backups/snapshots
- SSH security
- firewall rules
- server updates
- who has administrative access

## Export, backup, and deletion

The alpha CLI includes backup and restore for local runtime data. Deletion is currently filesystem-level: stop LearnBuddy, create any backup you need, then remove the runtime data directory. A friendlier delete/export workflow should exist before a broad non-technical release.

## What must never be committed

- real child answers or learning logs
- bot tokens
- chat IDs
- screenshots with identifying metadata
- private deployment paths
- provider credentials
- production backups
- private family notes

## For contributors

When adding tests, fixtures, docs, or issue examples, use synthetic data only. If a bug reproduction requires sensitive material, reduce it to a minimal synthetic reproduction before sharing.
