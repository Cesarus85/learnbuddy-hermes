"""Small CLI scaffold for LearnBuddy."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from .config import LearnBuddyConfig
from .delivery import DeliveryMessage, delivery_adapter_from_config
from .doctor import build_doctor_report, doctor_exit_code, format_text_report
from .exercise_packs import DEFAULT_PACK, available_packs, import_exercise_pack
from .maintenance import backup_runtime_data, create_setup, restore_runtime_data
from .material_import import build_material_from_file
from .notifier import ParentNotifier
from .runtime import LearnBuddyRuntime
from .telegram_answer_watcher import load_env_file, process_child_telegram_answers


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
        queue_max=config.queue_max,
        child_id=config.child_id,
        child_name=config.child_name,
        agent_name=config.agent_name,
    )


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def _delivery_succeeded(status: Any) -> bool:
    return str(status or "") in {"sent", "dry_run"}


def _parse_datetime(value: str | None, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(zone)
    return datetime.now(zone)


def _parse_clock(value: str) -> time:
    return time.fromisoformat(value)


def _inside_allowed_hours(now: datetime, start_text: str, end_text: str) -> bool:
    current = now.time().replace(second=0, microsecond=0)
    start = _parse_clock(start_text)
    end = _parse_clock(end_text)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _auto_sessions_today(runtime: LearnBuddyRuntime, now: datetime, timezone_name: str) -> int:
    zone = ZoneInfo(timezone_name)
    count = 0
    for session in runtime.sessions():
        if session.get("mode") != "auto":
            continue
        timestamp = session.get("timestamp")
        if not timestamp:
            continue
        session_time = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(zone)
        if session_time.date() == now.date():
            count += 1
    return count


def _deliver_pending_child_prompt(config: LearnBuddyConfig, runtime: LearnBuddyRuntime, *, force: bool = False) -> dict[str, Any]:
    state = runtime.status()
    pending = state.get("pending")
    if not isinstance(pending, dict):
        return {"status": "no_pending", "delivery": None, "session": None}
    child_delivery = pending.get("delivery", {}).get("child", {}) if isinstance(pending.get("delivery"), dict) else {}
    if _delivery_succeeded(child_delivery.get("status")) and not force:
        return {"status": "already_sent", "delivery": child_delivery, "session": pending}
    delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
        DeliveryMessage(
            text=str(pending.get("prompt") or ""),
            metadata={"kind": "pending_exercise", "session_id": pending.get("id")},
        )
    )
    delivery_dict = delivery.to_dict()
    updated = runtime.mark_pending_delivery(delivery_dict)
    return {
        "status": "sent" if _delivery_succeeded(delivery_dict.get("status")) else delivery_dict.get("status", "error"),
        "delivery": delivery_dict,
        "session": updated,
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    report = build_doctor_report(
        config,
        hermes_home=args.hermes_home,
        parent_profile=args.parent_profile,
        child_profile=args.child_profile,
        systemd_user_dir=args.systemd_user_dir,
        child_gateway_service=args.child_gateway_service,
        dispatch_timer_profile=args.dispatch_timer_profile,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text_report(report))
    return doctor_exit_code(report)


def cmd_setup(args: argparse.Namespace) -> int:
    result = create_setup(
        config_path=args.config,
        data_dir=args.data_dir,
        child_id=args.child_id,
        child_name=args.child_name,
        agent_name=args.agent_name,
        delivery_mode=args.delivery_mode,
        force=args.force,
    )
    if result.get("status") == "created" and args.exercise_pack:
        config = LearnBuddyConfig.from_yaml(result["config_path"])
        runtime = LearnBuddyRuntime(
            Path(result["storage_dir"]),
            max_attempts=config.max_attempts,
            queue_max=config.queue_max,
            child_id=config.child_id,
            child_name=config.child_name,
            agent_name=config.agent_name,
        )
        result["seed"] = import_exercise_pack(runtime, args.exercise_pack)
    if args.format == "json":
        _print_json(result)
    else:
        print(f"learnbuddy setup {result['status']}")
        for key in ("config_path", "storage_dir", "error"):
            if result.get(key):
                print(f"{key}={result[key]}")
    return 0 if result["status"] == "created" else 1


def cmd_seed(args: argparse.Namespace) -> int:
    if args.list:
        _print_json({"status": "ok", "available_packs": available_packs(), "default_pack": DEFAULT_PACK})
        return 0
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = import_exercise_pack(runtime, args.pack)
    _print_json(result)
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    data_dir = Path(getattr(args, "data_dir", None) or config.resolved_storage_dir())
    result = backup_runtime_data(data_dir=data_dir, output=args.output)
    _print_json(result)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    result = restore_runtime_data(archive=args.archive, data_dir=args.data_dir, force=args.force)
    _print_json(result)
    return 0 if result["status"] == "restored" else 1


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


def cmd_schedule_exercise(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = runtime.schedule_exercise({
        "subject": args.subject,
        "type": args.type,
        "prompt": args.prompt,
        "answer": args.answer,
    }, due_at=args.due_at)
    _print_json({"status": "scheduled", **result})
    return 0


def cmd_material(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    if args.material_command == "add-text":
        material = runtime.add_material_set({
            "title": args.title,
            "subject": args.subject,
            "source_type": "text",
            "text_excerpt": args.text,
            "task_candidates": args.candidate or [],
            "notes": args.notes or "",
        })
        _print_json({"status": "pending_review", "material": material})
        return 0
    if args.material_command == "add-file":
        import_result = build_material_from_file(
            args.file,
            title=args.title,
            subject=args.subject,
            notes=args.notes or "",
            ocr_command=args.ocr_command or os.getenv("LEARNBUDDY_MATERIAL_OCR_COMMAND"),
            max_bytes=args.max_bytes,
        )
        if import_result.get("status") != "ok":
            _print_json(import_result)
            return 1
        material = runtime.add_material_set(import_result["material"])
        _print_json({
            "status": "pending_review",
            "material": material,
            "extraction": import_result.get("extraction"),
            "preview": import_result.get("preview"),
        })
        return 0
    if args.material_command == "status":
        _print_json(runtime.material_status(limit=args.limit))
        return 0
    if args.material_command == "approve":
        result = runtime.approve_material_tasks(
            args.material_id,
            expected_answers=args.expected_answer or [],
            requested_by="parent",
        )
        _print_json(result)
        return 0 if result.get("status") == "approved" else 1
    raise ValueError(f"unsupported material command: {args.material_command}")


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
        delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
        result["delivery"] = delivery_result.get("delivery")
        result["delivery_status"] = delivery_result.get("status")
        result["session"] = delivery_result.get("session") or result.get("session")
    _print_json(result)
    return 0


def cmd_deliver_pending(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = _deliver_pending_child_prompt(config, runtime, force=args.force)
    _print_json(result)
    return 0 if result.get("status") in {"sent", "already_sent"} else 1


def cmd_dispatch_plan(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    now = _parse_datetime(args.now, config.timezone)
    if not _inside_allowed_hours(now, config.allowed_hours_from, config.allowed_hours_to):
        _print_json({
            "status": "outside_allowed_hours",
            "now": now.isoformat(),
            "allowed_hours": {"from": config.allowed_hours_from, "to": config.allowed_hours_to},
        })
        return 0
    state = runtime.status()
    if isinstance(state.get("pending"), dict):
        _print_json({"status": "pending_exists", "pending": state.get("pending")})
        return 0
    scheduled = None
    if not args.exercise_id and not args.subject:
        scheduled = runtime.next_due_scheduled_exercise(now=now.isoformat(), timezone_name=config.timezone)
        if scheduled is None and runtime.pending_scheduled_exercises():
            _print_json({"status": "no_due_scheduled_exercise", "now": now.isoformat()})
            return 0
    if scheduled is None and not args.exercise_id and not args.subject and runtime.active_learning_plan():
        result = runtime.dispatch_learning_plan(now=now.isoformat(), timezone_name=config.timezone)
        if result.get("status") == "opened":
            delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
            result["delivery"] = delivery_result.get("delivery")
            result["delivery_status"] = delivery_result.get("status")
            result["session"] = delivery_result.get("session") or result.get("session")
        _print_json(result)
        return 0
    auto_count = _auto_sessions_today(runtime, now, config.timezone)
    if scheduled is None and auto_count >= config.daily_auto_limit:
        _print_json({"status": "daily_limit_reached", "daily_auto_limit": config.daily_auto_limit, "auto_sessions_today": auto_count})
        return 0
    try:
        result = runtime.open_exercise(
            args.exercise_id or (str(scheduled.get("exercise_id")) if isinstance(scheduled, dict) else None),
            subject=args.subject,
            mode="auto",
            requested_by="system",
            timestamp=now.astimezone(ZoneInfo("UTC")).isoformat(),
            source="scheduled_exercise" if scheduled else None,
            scheduled_id=str(scheduled.get("id")) if isinstance(scheduled, dict) else None,
        )
    except KeyError as exc:
        _print_json({"status": "no_matching_exercise", "error": str(exc)})
        return 0
    if result.get("status") == "opened":
        delivery_result = _deliver_pending_child_prompt(config, runtime, force=True)
        result["delivery"] = delivery_result.get("delivery")
        result["delivery_status"] = delivery_result.get("status")
        result["session"] = delivery_result.get("session") or result.get("session")
        if scheduled:
            result["scheduled"] = runtime.mark_scheduled_exercise_dispatched(
                str(scheduled.get("id")),
                session_id=(result.get("session") or {}).get("id") if isinstance(result.get("session"), dict) else None,
                delivery_result=delivery_result.get("delivery"),
            )
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


def run_daily_parent_status(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    *,
    notify: bool = False,
    include_empty: bool = False,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Render and optionally deliver one bounded daily parent status report."""
    local_now = _parse_datetime(now, config.timezone)
    date_text = local_now.date().isoformat()
    automation = runtime.parent_automation_status(now=local_now.isoformat(), timezone_name=config.timezone)
    if automation.get("paused"):
        return {"status": "automation_paused", "automation": automation, "report": None, "notification": None}
    daily_state = runtime.daily_parent_status_state()
    if daily_state.get("last_sent_date") == date_text and not force:
        return {"status": "already_sent", "daily_status": daily_state, "report": None, "notification": None}
    report = runtime.parent_daily_report(now=local_now.isoformat(), timezone_name=config.timezone)
    if int(report.get("answers") or 0) == 0 and int(report.get("sessions_started") or 0) == 0 and not include_empty:
        daily = runtime.mark_daily_parent_status(date=date_text, status="no_activity")
        return {"status": "no_activity", "daily_status": daily, "report": report, "notification": None}
    notification = None
    status = "rendered"
    if notify:
        notification = ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_report(report).to_dict()
        status = "sent" if _delivery_succeeded(notification.get("status")) else str(notification.get("status") or "error")
    daily = runtime.mark_daily_parent_status(date=date_text, delivery_result=notification if status == "sent" else None, status=status)
    return {"status": status, "daily_status": daily, "report": report, "notification": notification}


def run_weekly_parent_status(
    config: LearnBuddyConfig,
    runtime: LearnBuddyRuntime,
    *,
    notify: bool = False,
    include_empty: bool = False,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Render and optionally deliver one bounded weekly parent status report."""
    local_now = _parse_datetime(now, config.timezone)
    automation = runtime.parent_automation_status(now=local_now.isoformat(), timezone_name=config.timezone)
    if automation.get("paused"):
        return {"status": "automation_paused", "automation": automation, "report": None, "notification": None}
    report = runtime.parent_weekly_report(now=local_now.isoformat(), timezone_name=config.timezone)
    week_key = str(report.get("week_key") or "")
    weekly_state = runtime.weekly_parent_status_state()
    if weekly_state.get("last_sent_week") == week_key and not force:
        return {"status": "already_sent", "weekly_status": weekly_state, "report": None, "notification": None}
    if int(report.get("answers") or 0) == 0 and int(report.get("sessions_started") or 0) == 0 and not include_empty:
        weekly = runtime.mark_weekly_parent_status(week_key=week_key, status="no_activity")
        return {"status": "no_activity", "weekly_status": weekly, "report": report, "notification": None}
    notification = None
    status = "rendered"
    if notify:
        notification = ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_report(report).to_dict()
        status = "sent" if _delivery_succeeded(notification.get("status")) else str(notification.get("status") or "error")
    weekly = runtime.mark_weekly_parent_status(week_key=week_key, delivery_result=notification if status == "sent" else None, status=status)
    return {"status": status, "weekly_status": weekly, "report": report, "notification": notification}


def cmd_daily_status(args: argparse.Namespace) -> int:
    load_env_file(os.getenv("LEARNBUDDY_ENV_FILE"))
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = run_daily_parent_status(
        config,
        runtime,
        notify=args.notify,
        include_empty=args.include_empty,
        force=args.force,
        now=args.now,
    )
    _print_json(result)
    return 0


def cmd_weekly_status(args: argparse.Namespace) -> int:
    load_env_file(os.getenv("LEARNBUDDY_ENV_FILE"))
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    result = run_weekly_parent_status(
        config,
        runtime,
        notify=args.notify,
        include_empty=args.include_empty,
        force=args.force,
        now=args.now,
    )
    _print_json(result)
    return 0


def cmd_automation(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    action = args.action.replace("-", "_")
    result = runtime.set_parent_automation(action, now=args.now, timezone_name=config.timezone, reason=args.reason)
    _print_json(result)
    return 0


def cmd_help_request(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    request = runtime.create_parent_help_request(
        args.reason,
        subject=args.subject,
        target=args.target,
        urgent=args.urgent,
        requested_by=args.requested_by,
    )
    if args.notify:
        request["notification"] = ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_help_request(request).to_dict()
    _print_json({"status": "created", "help_request": request})
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runtime = _runtime_from_args(args, config)
    action = args.plan_command.replace("-", "_")
    if action == "status":
        _print_json(runtime.learning_plan_status())
        return 0
    if action == "create":
        plan = runtime.create_learning_plan({
            "title": args.title,
            "subjects": args.subject or [],
            "focus": args.focus or [],
            "daily_goal": args.daily_goal,
            "created_by": args.created_by,
        })
        _print_json({"status": plan["status"], "plan": plan})
        return 0
    result = runtime.set_learning_plan(action, plan_id=args.plan_id, reason=args.reason)
    _print_json(result)
    return 0 if result.get("status") not in {"unknown_plan", "no_active_plan"} else 1


def cmd_watch_telegram_answers(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    result = process_child_telegram_answers(
        config,
        env_file=args.env_file,
        state_file=args.state_file,
        send_feedback=not args.no_feedback,
        notify_parent=not args.no_parent_notify,
    )
    _print_json(result)
    return 1 if result.get("status") == "error" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="learnbuddy")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check local LearnBuddy prerequisites")
    doctor.add_argument("--config", help="path to learnbuddy.yaml")
    doctor.add_argument("--format", choices=["text", "json"], default="text", help="doctor output format")
    doctor.add_argument("--hermes-home", help="Hermes home to inspect for profile onboarding checks")
    doctor.add_argument("--parent-profile", help="parent/admin Hermes profile to verify for LearnBuddy Telegram routing")
    doctor.add_argument("--child-profile", help="child Hermes profile to verify for locked-down LearnBuddy routing")
    doctor.add_argument("--systemd-user-dir", help="systemd user unit directory to inspect; defaults to ~/.config/systemd/user")
    doctor.add_argument("--child-gateway-service", help="child gateway systemd user service name, with or without .service")
    doctor.add_argument("--dispatch-timer-profile", help="profile label used by scripts/install-dispatch-timer.sh")
    doctor.set_defaults(func=cmd_doctor)
    setup = sub.add_parser("setup", help="create a public-safe starter config and storage directory")
    setup.add_argument("--config", default="learnbuddy.yaml", help="path to write learnbuddy.yaml")
    setup.add_argument("--data-dir", help="LearnBuddy storage directory to create")
    setup.add_argument("--child-id", default="learner")
    setup.add_argument("--child-name", default="Learner")
    setup.add_argument("--agent-name", default="LearnBuddy")
    setup.add_argument("--delivery-mode", choices=["dry_run", "telegram"], default="dry_run")
    setup.add_argument("--exercise-pack", help=f"optionally seed a bundled exercise pack, e.g. {DEFAULT_PACK}")
    setup.add_argument("--format", choices=["text", "json"], default="json")
    setup.add_argument("--force", action="store_true", help="overwrite an existing config file")
    setup.set_defaults(func=cmd_setup)

    seed = sub.add_parser("seed", help="import a bundled public-safe exercise pack into local storage")
    _add_runtime_options(seed)
    seed.add_argument("--pack", default=DEFAULT_PACK, help=f"exercise pack to import; default: {DEFAULT_PACK}")
    seed.add_argument("--list", action="store_true", help="list bundled exercise packs without importing")
    seed.set_defaults(func=cmd_seed)

    backup = sub.add_parser("backup", help="create a zip backup of local runtime data")
    _add_runtime_options(backup)
    backup.add_argument("--output", required=True, help="zip archive path to create")
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="restore a LearnBuddy runtime zip backup")
    restore.add_argument("--archive", required=True, help="backup zip archive to restore")
    restore.add_argument("--data-dir", required=True, help="target LearnBuddy storage directory")
    restore.add_argument("--force", action="store_true", help="overwrite existing runtime files")
    restore.set_defaults(func=cmd_restore)

    queue = sub.add_parser("queue", help="create an exercise in local LearnBuddy storage")
    _add_runtime_options(queue)
    queue.add_argument("--subject", default="general")
    queue.add_argument("--type", default="short")
    queue.add_argument("--prompt", required=True)
    queue.add_argument("--answer", required=True)
    queue.set_defaults(func=cmd_queue)

    schedule = sub.add_parser("schedule-exercise", help="create an exercise and dispatch it later via dispatch-plan")
    _add_runtime_options(schedule)
    schedule.add_argument("--subject", default="general")
    schedule.add_argument("--type", default="short")
    schedule.add_argument("--prompt", required=True)
    schedule.add_argument("--answer", required=True)
    schedule.add_argument("--due-at", required=True, help="ISO timestamp when dispatch-plan may deliver the exercise")
    schedule.set_defaults(func=cmd_schedule_exercise)

    material = sub.add_parser("material", help="add, review, and approve parent-supplied learning material")
    material_sub = material.add_subparsers(dest="material_command", required=True)
    material_add = material_sub.add_parser("add-text", help="store parent-supplied text material for review")
    _add_runtime_options(material_add)
    material_add.add_argument("--title", required=True)
    material_add.add_argument("--subject", choices=["math", "german", "english", "general"], default="general")
    material_add.add_argument("--text", required=True, help="public-safe extracted/pasted material text")
    material_add.add_argument("--candidate", action="append", help="reviewable task candidate; repeat for multiple tasks")
    material_add.add_argument("--notes", help="short parent/admin note")
    material_add.set_defaults(func=cmd_material)
    material_file = material_sub.add_parser("add-file", help="extract text/candidates from a local worksheet photo, PDF, or text file for parent review")
    _add_runtime_options(material_file)
    material_file.add_argument("--title", required=True)
    material_file.add_argument("--subject", choices=["math", "german", "english", "general"], default="general")
    material_file.add_argument("--file", required=True, help="local material file path (.jpg/.png/.webp/.pdf/.txt/.md/.csv)")
    material_file.add_argument("--ocr-command", help="optional OCR/vision command for images; receives the file path as final argv item; can also use LEARNBUDDY_MATERIAL_OCR_COMMAND")
    material_file.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024, help="maximum accepted upload/file size before extraction")
    material_file.add_argument("--notes", help="short parent/admin note")
    material_file.set_defaults(func=cmd_material)
    material_status = material_sub.add_parser("status", help="show material review queue")
    _add_runtime_options(material_status)
    material_status.add_argument("--limit", type=int, default=10)
    material_status.set_defaults(func=cmd_material)
    material_approve = material_sub.add_parser("approve", help="convert reviewed material candidates into bounded exercises")
    _add_runtime_options(material_approve)
    material_approve.add_argument("--material-id", required=True)
    material_approve.add_argument("--expected-answer", action="append", help="expected answer matching each task candidate; repeat in order")
    material_approve.set_defaults(func=cmd_material)

    next_exercise = sub.add_parser("next", help="open or queue the next exercise")
    _add_runtime_options(next_exercise)
    next_exercise.add_argument("--exercise-id")
    next_exercise.add_argument("--subject")
    next_exercise.add_argument("--mode", default="manual")
    next_exercise.add_argument("--requested-by", default="parent")
    next_exercise.add_argument("--deliver", action="store_true")
    next_exercise.set_defaults(func=cmd_next)

    deliver_pending = sub.add_parser("deliver-pending", help="send or repair delivery of the current pending exercise")
    _add_runtime_options(deliver_pending)
    deliver_pending.add_argument("--force", action="store_true", help="send again even if the pending exercise is already marked delivered")
    deliver_pending.set_defaults(func=cmd_deliver_pending)

    dispatch_plan = sub.add_parser("dispatch-plan", help="open and deliver one due automatic exercise when schedule policy allows it")
    _add_runtime_options(dispatch_plan)
    dispatch_plan.add_argument("--exercise-id")
    dispatch_plan.add_argument("--subject")
    dispatch_plan.add_argument("--now", help="ISO timestamp override for tests or controlled scheduler runs")
    dispatch_plan.set_defaults(func=cmd_dispatch_plan)

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

    daily_status = sub.add_parser("daily-status", help="render/send one daily parent status report with duplicate and pause guards")
    _add_runtime_options(daily_status)
    daily_status.add_argument("--notify", action="store_true", help="deliver the daily status to the configured parent adapter")
    daily_status.add_argument("--include-empty", action="store_true", help="send even when no answers were recorded for the local day")
    daily_status.add_argument("--force", action="store_true", help="ignore the once-per-day send guard")
    daily_status.add_argument("--now", help="ISO timestamp override for tests or controlled scheduler runs")
    daily_status.set_defaults(func=cmd_daily_status)

    weekly_status = sub.add_parser("weekly-status", help="render/send one weekly parent report with recommendations and duplicate guards")
    _add_runtime_options(weekly_status)
    weekly_status.add_argument("--notify", action="store_true", help="deliver the weekly status to the configured parent adapter")
    weekly_status.add_argument("--include-empty", action="store_true", help="send even when no sessions or answers were recorded for the local week")
    weekly_status.add_argument("--force", action="store_true", help="ignore the once-per-week send guard")
    weekly_status.add_argument("--now", help="ISO timestamp override for tests or controlled scheduler runs")
    weekly_status.set_defaults(func=cmd_weekly_status)

    automation = sub.add_parser("automation", help="inspect or control parent-facing scheduled automation")
    _add_runtime_options(automation)
    automation.add_argument("action", choices=["status", "pause-today", "resume"])
    automation.add_argument("--reason", help="short parent-facing reason for pausing today")
    automation.add_argument("--now", help="ISO timestamp override for tests or controlled scheduler runs")
    automation.set_defaults(func=cmd_automation)

    help_request = sub.add_parser("help-request", help="record a bounded parent-help request")
    _add_runtime_options(help_request)
    help_request.add_argument("--reason", required=True)
    help_request.add_argument("--subject", choices=["math", "german", "english", "general"])
    help_request.add_argument("--target", choices=["parents", "primary_parent"], default="parents")
    help_request.add_argument("--requested-by", choices=["child", "parent", "system"], default="child")
    help_request.add_argument("--urgent", action="store_true")
    help_request.add_argument("--notify", action="store_true")
    help_request.set_defaults(func=cmd_help_request)

    plan = sub.add_parser("plan", help="create, inspect, pause, resume, or complete learning plans")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    plan_create = plan_sub.add_parser("create", help="create and activate a parent-approved learning plan")
    _add_runtime_options(plan_create)
    plan_create.add_argument("--title", required=True)
    plan_create.add_argument("--subject", action="append", choices=["math", "german", "english", "general"], help="subject allowed by this plan; repeatable")
    plan_create.add_argument("--focus", action="append", help="short focus/topic label; repeatable")
    plan_create.add_argument("--daily-goal", type=int, default=1, help="maximum plan-dispatched exercises per local day")
    plan_create.add_argument("--created-by", choices=["parent", "system"], default="parent")
    plan_create.set_defaults(func=cmd_plan)
    plan_status = plan_sub.add_parser("status", help="show active and historical learning plans")
    _add_runtime_options(plan_status)
    plan_status.set_defaults(func=cmd_plan)
    for action_name in ("pause", "resume", "complete", "cancel"):
        action_parser = plan_sub.add_parser(action_name, help=f"{action_name} the active or selected learning plan")
        _add_runtime_options(action_parser)
        action_parser.add_argument("--plan-id", help="specific plan id; defaults to active plan")
        action_parser.add_argument("--reason", help="short parent-facing reason")
        action_parser.set_defaults(func=cmd_plan)

    watch = sub.add_parser("watch-telegram-answers", help="process one pending child Telegram answer")
    watch.add_argument("--config", help="path to learnbuddy.yaml")
    watch.add_argument("--env-file", help="optional KEY=VALUE file for Telegram env vars")
    watch.add_argument("--state-file", help="optional watcher offset state file")
    watch.add_argument("--no-feedback", action="store_true", help="do not send child feedback")
    watch.add_argument("--no-parent-notify", action="store_true", help="do not notify parent of the answer result")
    watch.set_defaults(func=cmd_watch_telegram_answers)
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
