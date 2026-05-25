# Contributing

This project is early. Contributions should preserve the child-safety model.

## Rules

- No real child data in commits.
- No tokens, chat IDs, screenshots with identifying metadata, or production logs.
- Add tests for evaluator, queue, delivery, and setup-safety changes.
- Keep child-facing tools bounded.
- Prefer boring, auditable code over clever magic.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
```
