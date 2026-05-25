# Privacy

LearnBuddy is designed as self-hosted software. The project maintainers should not receive family learning data by default.

## Data that a local installation may store

Depending on configuration:

- child display name or nickname
- grade/school-context settings
- exercises
- answers
- attempt counts
- parent settings
- delivery events
- learning plans

## Data minimization

- Do not store raw chat logs as the default product view.
- Prefer learning aggregates over shameful error lists.
- Keep examples synthetic.
- Do not add telemetry in the MVP.

## Deletion and export

The project must provide local export/delete tooling before a non-technical public release.

## Cloud LLMs and VPS hosting

If families use a cloud LLM or VPS provider, learning content may be processed or stored by that provider depending on its terms. Documentation must make this explicit and help families choose privacy-preserving settings.
