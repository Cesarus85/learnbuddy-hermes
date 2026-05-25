"""Small CLI scaffold for LearnBuddy."""
from __future__ import annotations

import argparse
from pathlib import Path
from .config import default_storage_dir


def cmd_doctor(args: argparse.Namespace) -> int:
    storage = default_storage_dir()
    print("LearnBuddy doctor")
    print(f"storage_dir={storage}")
    print(f"storage_exists={storage.exists()}")
    print("status=pre-alpha scaffold")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    print("learnbuddy setup is not implemented yet.")
    print("This scaffold intentionally does not touch Hermes profiles or Telegram tokens yet.")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="learnbuddy")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check local LearnBuddy prerequisites")
    doctor.set_defaults(func=cmd_doctor)
    setup = sub.add_parser("setup", help="interactive setup wizard (planned)")
    setup.set_defaults(func=cmd_setup)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
