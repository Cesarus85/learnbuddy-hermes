"""Small CLI scaffold for LearnBuddy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from .config import LearnBuddyConfig
from .delivery import DeliveryMessage, delivery_adapter_from_config
from .doctor import build_doctor_report, doctor_exit_code, format_text_report
from .notifier import ParentNotifier
from .runtime import LearnBuddyRuntime


def _config_from_args(args: argparse.Namespace) -> LearnBuddyConfig:
    config_path = getattr(args, "config", None)
    if config_path:
        return LearnBuddyConfig.from_yaml(config_path)
    return LearnBuddyConfig()


def _runtime_from_args(args: argparse.Namespace, config: LearnBuddyConfig | None = None) -> LearnBuddyRuntime:
    config = config or _config_from_args(args)
    data_dir = Path(getattr(args, "data_dir", None) or config.resolved_storage_dir())
    return LearnBuddyRuntime(
        data_dir,
        max_attempts=config.max_attempts,
        child_id=config.child_id,
        child_name=config.child_name,
        agent_name=config.agent_name,
    )


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    report = build_doctor_report(config)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text_report(report))
    return doctor_exit_code(report)


def cmd_setup(args: argparse.Namespace) -> int:
    print("learnbuddy setup is not implemented yet.")
    print("This scaffold intentionally does not touch Hermes profiles or Telegram tokens yet.")
    return 2


def cmd_queue(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    exercise = runtime.add_exercise({
        "subject": args.subject,
        "type": args.type,
        "prompt": args.prompt,
        "answer": args.answer,
    })
    _print_json({"status": "created", "exercise": exercise})
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = runtime.open_exercise(
        args.exercise_id,
        subject=args.subject,
        mode=args.mode,
        requested_by=args.requested_by,
    )
    if args.deliver and result.get("status") == "opened":
        delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
            DeliveryMessage(
                text=str(result.get("prompt") or ""),
                metadata={"session_id": result.get("session", {}).get("id")},
            )
        )
        result["delivery"] = delivery.to_dict()
    _print_json(result)
    return 0


def cmd_answer(args: argparse.Namespace) -> int:
    runtime = _runtime_from_args(args)
    _print_json(runtime.submit_answer(args.answer, input_mode=args.input_mode))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    runtime = _runtime_from_args(args)
    _print_json(runtime.status())
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    report = runtime.parent_report()
    if args.notify:
        report["notification"] = ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_report(report).to_dict()
    _print_json(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="learnbuddy")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check local LearnBuddy prerequisites")
    doctor.add_argument("--config", help="path to learnbuddy.yaml")
    doctor.add_argument("--format", choices=["text", "json"], default="text", help="doctor output format")
    doctor.set_defaults(func=cmd_doctor)
    setup = sub.add_parser("setup", help="interactive setup wizard (planned)")
    setup.set_defaults(func=cmd_setup)

    queue = sub.add_parser("queue", help="create an exercise in local LearnBuddy storage")
    _add_runtime_options(queue)
    queue.add_argument("--subject", default="general")
    queue.add_argument("--type", default="short")
    queue.add_argument("--prompt", required=True)
    queue.add_argument("--answer", required=True)
    queue.set_defaults(func=cmd_queue)

    next_exercise = sub.add_parser("next", help="open or queue the next exercise")
    _add_runtime_options(next_exercise)
    next_exercise.add_argument("--exercise-id")
    next_exercise.add_argument("--subject")
    next_exercise.add_argument("--mode", default="manual")
    next_exercise.add_argument("--requested-by", default="parent")
    next_exercise.add_argument("--deliver", action="store_true")
    next_exercise.set_defaults(func=cmd_next)

    answer = sub.add_parser("answer", help="submit an answer for the pending exercise")
    _add_runtime_options(answer)
    answer.add_argument("answer")
    answer.add_argument("--input-mode", default="text")
    answer.set_defaults(func=cmd_answer)

    status = sub.add_parser("status", help="show pending and queue state")
    _add_runtime_options(status)
    status.set_defaults(func=cmd_status)

    report = sub.add_parser("report", help="render a parent report")
    _add_runtime_options(report)
    report.add_argument("--notify", action="store_true")
    report.set_defaults(func=cmd_report)
    return parser


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="path to learnbuddy.yaml")
    parser.add_argument("--data-dir", help="override configured LearnBuddy storage dir")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
