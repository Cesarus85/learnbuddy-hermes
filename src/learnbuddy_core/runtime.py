"""Small JSON/JSONL runtime for the public LearnBuddy MVP.

This module is intentionally deterministic and filesystem-local. It is designed
for synthetic fixtures and isolated HERMES_HOME tests first; production child
profiles can be wired to it later through adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import json
import uuid

from .evaluator import evaluate_answer


@dataclass(frozen=True)
class RuntimePaths:
    data_dir: Path

    @property
    def exercises(self) -> Path:
        return self.data_dir / "exercises.jsonl"

    @property
    def sessions(self) -> Path:
        return self.data_dir / "sessions.jsonl"

    @property
    def answers(self) -> Path:
        return self.data_dir / "answers.jsonl"

    @property
    def help_requests(self) -> Path:
        return self.data_dir / "help_requests.jsonl"

    @property
    def scheduled_exercises(self) -> Path:
        return self.data_dir / "scheduled_exercises.jsonl"

    @property
    def state(self) -> Path:
        return self.data_dir / "state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_datetime(value: str | None, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(zone)
    return datetime.now(zone)


def _same_local_date(timestamp: Any, target: datetime, timezone_name: str) -> bool:
    if not timestamp:
        return False
    try:
        return _local_datetime(str(timestamp), timezone_name).date() == target.date()
    except ValueError:
        return False


def _one_line(value: Any, *, max_len: int = 220) -> str:
    text = " ".join(str(value or "—").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _latest_answers_by_exercise(answers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    histories: dict[str, list[dict[str, Any]]] = {}
    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, row in enumerate(answers):
        key = str(row.get("exercise_id") or f"__row_{index}")
        if key not in histories:
            histories[key] = []
            order.append(key)
        histories[key].append(row)
        latest[key] = row
    return [latest[key] for key in order], histories


def _row_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _subject_label(subject: Any) -> str:
    labels = {"math": "Mathe", "german": "Deutsch", "english": "Englisch", "general": "Allgemein"}
    key = str(subject or "general")
    return labels.get(key, key)


def _short_local_date(timestamp: Any, timezone_name: str) -> str | None:
    if not timestamp:
        return None
    try:
        return _local_datetime(str(timestamp), timezone_name).strftime("%d.%m.")
    except ValueError:
        raw = str(timestamp)
        return raw[:10] if len(raw) >= 10 else None


def _week_bounds(local_now: datetime) -> tuple[datetime, datetime, str]:
    start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    return start, end, f"{start.date().isoformat()}/{end.date().isoformat()}"


def _inside_local_range(timestamp: Any, start: datetime, end: datetime, timezone_name: str) -> bool:
    if not timestamp:
        return False
    try:
        local_timestamp = _local_datetime(str(timestamp), timezone_name)
    except ValueError:
        return False
    return start <= local_timestamp <= end


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def _fresh_delivery_state() -> dict[str, Any]:
    return {"child": {"status": "not_attempted", "attempts": 0}}


def _normalize_session_delivery(session: dict[str, Any]) -> dict[str, Any]:
    delivery = session.get("delivery")
    if not isinstance(delivery, dict):
        delivery = {}
    child = delivery.get("child")
    if not isinstance(child, dict):
        child = {"status": "not_attempted", "attempts": 0}
    else:
        child.setdefault("status", "not_attempted")
        child.setdefault("attempts", 0)
    delivery["child"] = child
    session["delivery"] = delivery
    return session


class LearnBuddyRuntime:

    """Local state machine for one bounded LearnBuddy child profile."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        max_attempts: int = 3,
        child_id: str = "learner",
        child_name: str = "Learner",
        agent_name: str = "LearnBuddy",
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.paths = RuntimePaths(Path(data_dir).expanduser())
        self.max_attempts = max_attempts
        self.child_id = child_id
        self.child_name = child_name
        self.agent_name = agent_name
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.paths.state.exists():
            self._write_state({"pending": None, "queue": [], "profile": self._profile()})

    @property
    def data_dir(self) -> Path:
        return self.paths.data_dir

    def add_exercise(self, exercise: dict[str, Any]) -> dict[str, Any]:
        row = dict(exercise)
        row.setdefault("id", f"ex-{uuid.uuid4().hex[:12]}")
        row.setdefault("type", "short")
        row.setdefault("subject", "general")
        row.setdefault("created_at", _now())
        if "prompt" not in row:
            raise ValueError("exercise requires prompt")
        if "answer" not in row and "expected_answers" not in row:
            raise ValueError("exercise requires answer or expected_answers")
        _append_jsonl(self.paths.exercises, row)
        return row

    def exercises(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.paths.exercises)

    def scheduled_exercises(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.paths.scheduled_exercises)

    def sessions(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.paths.sessions)

    def status(self) -> dict[str, Any]:
        return self._state()

    def schedule_exercise(self, exercise: dict[str, Any], *, due_at: str) -> dict[str, Any]:
        """Create an exercise and record a one-shot parent-scheduled dispatch time."""
        due = _local_datetime(str(due_at), "Europe/Berlin")
        exercise_row = self.add_exercise(exercise)
        row = {
            "id": f"sched-{uuid.uuid4().hex[:12]}",
            "exercise_id": exercise_row["id"],
            "due_at": due.isoformat(),
            "status": "pending",
            "created_at": _now(),
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
        }
        _append_jsonl(self.paths.scheduled_exercises, row)
        return {"scheduled": row, "exercise": exercise_row}

    def pending_scheduled_exercises(self) -> list[dict[str, Any]]:
        return [row for row in self.scheduled_exercises() if row.get("status") in (None, "", "pending")]

    def next_due_scheduled_exercise(self, *, now: str | None = None, timezone_name: str = "Europe/Berlin") -> dict[str, Any] | None:
        current = _local_datetime(now, timezone_name)
        due_rows: list[dict[str, Any]] = []
        for row in self.pending_scheduled_exercises():
            try:
                due = _local_datetime(str(row.get("due_at") or ""), timezone_name)
            except ValueError:
                continue
            if due <= current:
                due_rows.append(row)
        due_rows.sort(key=lambda item: str(item.get("due_at") or ""))
        return due_rows[0] if due_rows else None

    def mark_scheduled_exercise_dispatched(
        self,
        schedule_id: str,
        *,
        session_id: str | None = None,
        delivery_result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self.scheduled_exercises()
        for index, row in enumerate(rows):
            if str(row.get("id") or "") != str(schedule_id):
                continue
            row = dict(row)
            row.update({"status": "dispatched", "dispatched_at": _now(), "session_id": session_id})
            if delivery_result is not None:
                row["delivery"] = delivery_result
            rows[index] = row
            _write_jsonl(self.paths.scheduled_exercises, rows)
            return row
        return None

    def mark_pending_delivery(self, delivery_result: dict[str, Any], *, recipient: str = "child") -> dict[str, Any] | None:
        """Persist user-visible delivery metadata for the current pending session."""
        if recipient != "child":
            raise ValueError(f"unsupported delivery recipient: {recipient}")
        state = self._state()
        pending = state.get("pending")
        if not isinstance(pending, dict):
            return None
        pending = _normalize_session_delivery(pending)
        previous = pending["delivery"].get(recipient, {})
        attempts = int(previous.get("attempts", 0)) + 1 if isinstance(previous, dict) else 1
        status = str(delivery_result.get("status") or "unknown")
        record = {
            "status": status,
            "adapter": delivery_result.get("adapter"),
            "target": delivery_result.get("target"),
            "message_id": delivery_result.get("message_id"),
            "error": delivery_result.get("error"),
            "attempts": attempts,
            "attempted_at": _now(),
        }
        if status in {"sent", "dry_run"}:
            record["delivered_at"] = record["attempted_at"]
        pending["delivery"][recipient] = record
        state["pending"] = pending
        self._write_state(state)
        return pending

    def open_exercise(
        self,
        exercise_id: str | None = None,
        *,
        subject: str | None = None,
        mode: str = "manual",
        requested_by: str = "parent",
        timestamp: str | None = None,
        source: str | None = None,
        scheduled_id: str | None = None,
    ) -> dict[str, Any]:
        exercise = self._choose_exercise(exercise_id=exercise_id, subject=subject)
        state = self._state()
        session = self._make_session(
            exercise,
            mode=mode,
            requested_by=requested_by,
            timestamp=timestamp,
            source=source,
            scheduled_id=scheduled_id,
        )
        if state.get("pending"):
            queue_item = dict(session)
            queue_item["queued_at"] = _now()
            state.setdefault("queue", []).append(queue_item)
            self._write_state(state)
            return {"status": "queued", "session": queue_item, "exercise": exercise}
        state["pending"] = session
        self._write_state(state)
        _append_jsonl(self.paths.sessions, session)
        return {"status": "opened", "session": session, "exercise": exercise, "prompt": exercise.get("prompt")}

    def submit_answer(self, answer: Any, *, input_mode: str = "text", timestamp: str | None = None) -> dict[str, Any]:
        state = self._state()
        pending = state.get("pending")
        if not pending:
            return {"result": "no_pending", "correct": False, "feedback": "Keine offene Aufgabe."}
        exercise = self._exercise_by_id(pending["exercise_id"])
        evaluation = evaluate_answer(
            answer,
            answer=exercise.get("answer"),
            expected_answers=exercise.get("expected_answers"),
            aliases=exercise.get("aliases"),
            prompt=str(exercise.get("prompt") or pending.get("prompt") or ""),
            exercise_type=str(exercise.get("type") or pending.get("type") or ""),
            subject=str(exercise.get("subject") or pending.get("subject") or ""),
            previous_attempts=int(pending.get("attempts", 0)),
            max_attempts=self.max_attempts,
        )
        pending["attempts"] = evaluation.attempts
        result = "correct" if evaluation.correct else "exhausted" if evaluation.exhausted else "retry"
        answer_row = {
            "timestamp": timestamp or _now(),
            "exercise_id": exercise["id"],
            "session_id": pending["id"],
            "child_id": pending.get("child_id", self.child_id),
            "child_name": pending.get("child_name", self.child_name),
            "agent_name": pending.get("agent_name", self.agent_name),
            "subject": exercise.get("subject", "general"),
            "type": exercise.get("type", "short"),
            "answer": str(answer),
            "expected": evaluation.canonical_answer,
            "correct": evaluation.correct,
            "attempts": evaluation.attempts,
            "max_attempts": evaluation.max_attempts,
            "exhausted": evaluation.exhausted,
            "result": result,
            "input_mode": input_mode,
            "metadata": evaluation.metadata,
        }
        _append_jsonl(self.paths.answers, answer_row)
        promoted_session = None
        if evaluation.correct or evaluation.exhausted:
            state["pending"] = None
            promoted_session = self._promote_next(state)
        else:
            state["pending"] = pending
        self._write_state(state)
        return {
            "result": result,
            "correct": evaluation.correct,
            "attempts": evaluation.attempts,
            "max_attempts": evaluation.max_attempts,
            "exhausted": evaluation.exhausted,
            "feedback": evaluation.feedback,
            "metadata": evaluation.metadata,
            "answer": answer_row,
            "answer_record": answer_row,
            "promoted_session": promoted_session,
        }

    def parent_report(self) -> dict[str, Any]:
        answers = _read_jsonl(self.paths.answers)
        correct = sum(1 for row in answers if row.get("correct") is True)
        exhausted = sum(1 for row in answers if row.get("exhausted") is True)
        subjects: dict[str, dict[str, int]] = {}
        for row in answers:
            subject = str(row.get("subject") or "general")
            bucket = subjects.setdefault(subject, {"answers": 0, "correct": 0})
            bucket["answers"] += 1
            if row.get("correct") is True:
                bucket["correct"] += 1
        total = len(answers)
        text = f"{self.agent_name} Status für {self.child_name}: {correct}/{total} richtig, {exhausted} Aufgaben mit aufgebrauchten Versuchen."
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "answers": total,
            "correct": correct,
            "exhausted": exhausted,
            "subjects": subjects,
            "text": text,
        }

    def parent_daily_report(self, *, now: str | None = None, timezone_name: str = "Europe/Berlin") -> dict[str, Any]:
        """Render a canonical parent report for activity on one local day."""
        local_now = _local_datetime(now, timezone_name)
        date_text = local_now.date().isoformat()
        all_sessions = _read_jsonl(self.paths.sessions)
        sessions_today = [row for row in all_sessions if _same_local_date(row.get("timestamp"), local_now, timezone_name)]
        answers_today = [row for row in _read_jsonl(self.paths.answers) if _same_local_date(row.get("timestamp"), local_now, timezone_name)]
        final_answers, histories = _latest_answers_by_exercise(answers_today)
        sessions_by_exercise = {str(row.get("exercise_id") or ""): row for row in all_sessions if row.get("exercise_id")}
        correct = sum(1 for row in final_answers if row.get("correct") is True)
        exhausted = sum(1 for row in final_answers if row.get("exhausted") is True)
        subjects: dict[str, dict[str, int]] = {}
        for row in final_answers:
            subject = str(row.get("subject") or "general")
            bucket = subjects.setdefault(subject, {"answers": 0, "correct": 0})
            bucket["answers"] += 1
            if row.get("correct") is True:
                bucket["correct"] += 1

        lines = [f"📚 {self.agent_name} Tagesstatus für {self.child_name} ({date_text})"]
        lines.append(f"- Heute neu gestartete Aufgaben: {len(sessions_today)}")
        if answers_today:
            lines.append(f"- Heute beantwortete Aufgaben: {len(final_answers)}")
            if len(answers_today) != len(final_answers):
                lines.append(f"- Antworten/Versuche insgesamt: {len(answers_today)}")
            lines.append("\nBeantwortete Aufgaben:")
            lines.extend(self._daily_answer_detail_lines(final_answers, histories, sessions_by_exercise, timezone_name=timezone_name))
            lines.append(f"\nGesamt heute: {correct}/{len(final_answers)} Aufgaben final richtig")
            for subject, total in sorted(subjects.items()):
                lines.append(f"- {_subject_label(subject)}: {total['correct']}/{total['answers']} richtig")
        else:
            lines.append("- Antworten: noch keine abgegeben")
        review_topics = [
            str(row.get("topic") or row.get("type") or row.get("subject") or "unklar")
            for row in final_answers
            if row.get("correct") is not True
        ]
        if review_topics:
            seen: list[str] = []
            for topic in review_topics:
                if topic not in seen:
                    seen.append(topic)
            lines.append("- Sanft wiederholen: " + ", ".join(seen[:3]))
        lines.append("\nElternbericht — mit Aufgaben und Antwort, ohne unnötige Rohdaten.")
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "date": date_text,
            "timezone": timezone_name,
            "sessions_started": len(sessions_today),
            "answers": len(final_answers),
            "answer_attempts": len(answers_today),
            "correct": correct,
            "exhausted": exhausted,
            "subjects": subjects,
            "text": "\n".join(lines),
        }

    def parent_weekly_report(self, *, now: str | None = None, timezone_name: str = "Europe/Berlin") -> dict[str, Any]:
        """Render a parent weekly report with bounded recommendations for the current local week."""
        local_now = _local_datetime(now, timezone_name)
        week_start, week_end, week_key = _week_bounds(local_now)
        all_sessions = _read_jsonl(self.paths.sessions)
        sessions_week = [row for row in all_sessions if _inside_local_range(row.get("timestamp"), week_start, week_end, timezone_name)]
        answers_week = [row for row in _read_jsonl(self.paths.answers) if _inside_local_range(row.get("timestamp"), week_start, week_end, timezone_name)]
        final_answers, histories = _latest_answers_by_exercise(answers_week)
        sessions_by_exercise = {str(row.get("exercise_id") or ""): row for row in all_sessions if row.get("exercise_id")}
        correct = sum(1 for row in final_answers if row.get("correct") is True)
        exhausted = sum(1 for row in final_answers if row.get("exhausted") is True)
        subjects: dict[str, dict[str, int]] = {}
        review_topics: list[str] = []
        for row in final_answers:
            subject = str(row.get("subject") or "general")
            bucket = subjects.setdefault(subject, {"answers": 0, "correct": 0})
            bucket["answers"] += 1
            if row.get("correct") is True:
                bucket["correct"] += 1
            else:
                topic = str(row.get("topic") or row.get("type") or row.get("subject") or "unklar")
                if topic not in review_topics:
                    review_topics.append(topic)

        recommendations: list[str] = []
        if review_topics:
            recommendations.append("Nächste Woche sanft wiederholen: " + ", ".join(review_topics[:3]))
        if subjects:
            weakest = sorted(subjects.items(), key=lambda item: (item[1]["correct"] / max(item[1]["answers"], 1), item[0]))[0]
            if weakest[1]["answers"] and weakest[1]["correct"] < weakest[1]["answers"]:
                recommendations.append(f"Etwas mehr {_subject_label(weakest[0])} einplanen, aber kurz halten.")
        if not recommendations and final_answers:
            recommendations.append("Nächste Woche ähnlich weitermachen und eine kleine Stufe schwerer versuchen.")
        if not recommendations:
            recommendations.append("Noch keine Lernaktivität in dieser Woche — erst eine kurze Aufgabe starten.")

        lines = [
            f"📚 {self.agent_name} Wochenbericht für {self.child_name} ({week_start.date().isoformat()}–{week_end.date().isoformat()})",
            f"- Neu gestartete Aufgaben: {len(sessions_week)}",
            f"- Final beantwortete Aufgaben: {len(final_answers)}",
        ]
        if len(answers_week) != len(final_answers):
            lines.append(f"- Antworten/Versuche insgesamt: {len(answers_week)}")
        if final_answers:
            lines.append(f"- Gesamt: {correct}/{len(final_answers)} Aufgaben final richtig")
            for subject, total in sorted(subjects.items()):
                lines.append(f"- {_subject_label(subject)}: {total['correct']}/{total['answers']} richtig")
            lines.append("\nBeantwortete Aufgaben diese Woche:")
            lines.extend(self._daily_answer_detail_lines(final_answers, histories, sessions_by_exercise, timezone_name=timezone_name))
        else:
            lines.append("- Antworten: noch keine abgegeben")
        lines.append("\nEmpfehlungen:")
        lines.extend(f"- {item}" for item in recommendations)
        lines.append("\nWochenbericht — kompakt, parent-facing, ohne rohe Chatlogs.")
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "week_start": week_start.date().isoformat(),
            "week_end": week_end.date().isoformat(),
            "week_key": week_key,
            "timezone": timezone_name,
            "sessions_started": len(sessions_week),
            "answers": len(final_answers),
            "answer_attempts": len(answers_week),
            "correct": correct,
            "exhausted": exhausted,
            "subjects": subjects,
            "recommendations": recommendations,
            "text": "\n".join(lines),
        }

    def _daily_answer_detail_lines(
        self,
        answers: list[dict[str, Any]],
        histories: dict[str, list[dict[str, Any]]],
        sessions_by_exercise: dict[str, dict[str, Any]],
        *,
        timezone_name: str,
    ) -> list[str]:
        lines: list[str] = []
        for index, row in enumerate(answers, 1):
            exercise_id = str(row.get("exercise_id") or "")
            exercise = self._exercise_by_id_or_none(exercise_id) or {}
            session = sessions_by_exercise.get(exercise_id, {})
            prompt = _one_line(row.get("prompt") or exercise.get("prompt") or session.get("prompt") or "Aufgabe nicht mehr auffindbar")
            subject = _subject_label(row.get("subject") or exercise.get("subject"))
            verdict = "richtig" if row.get("correct") else "noch nicht richtig"
            attempts = row.get("attempts")
            max_attempts = row.get("max_attempts") or self.max_attempts
            suffix = ""
            if attempts not in (None, ""):
                if (not row.get("correct")) and row.get("exhausted"):
                    suffix = f", Versuch {attempts}/{max_attempts} — alle Versuche aufgebraucht"
                else:
                    suffix = f", Versuch {attempts}"
            started_note = ""
            if session.get("timestamp") and not _same_local_date(session.get("timestamp"), _local_datetime(str(row.get("timestamp")), timezone_name), timezone_name):
                short_date = _short_local_date(session.get("timestamp"), timezone_name)
                if short_date:
                    started_note = f" — gestellt am {short_date}"
            lines.append(f"{index}. {subject}{started_note}: {prompt}")
            lines.append(f"   {self.child_name}: {_one_line(row.get('answer'), max_len=260)}")
            history = histories.get(exercise_id, [])
            if len(history) > 1:
                previous = ", ".join(_one_line(previous_row.get("answer"), max_len=60) for previous_row in history[:-1])
                if previous:
                    lines.append(f"   Vorherige Versuche: {previous}")
            metadata = _row_metadata(row)
            score = metadata.get("score", row.get("score"))
            total = metadata.get("total", row.get("total"))
            if score not in (None, "") and total not in (None, ""):
                lines.append(f"   Teilaufgaben: {score}/{total} richtig")
            item_results = metadata.get("item_results", row.get("item_results", []))
            wrong_items = [str(item.get("index")) for item in item_results if isinstance(item, dict) and not item.get("correct")]
            if wrong_items:
                lines.append(f"   Nochmal anschauen: Nr. {', '.join(wrong_items[:6])}{' …' if len(wrong_items) > 6 else ''}")
            lines.append(f"   Ergebnis: {verdict}{suffix}")
        return lines

    def parent_automation_status(self, *, now: str | None = None, timezone_name: str = "Europe/Berlin") -> dict[str, Any]:
        """Return whether scheduled parent automation is paused for the local day."""
        state = self._state()
        automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        local_now = _local_datetime(now, timezone_name)
        pause_date = automation.get("pause_date")
        indefinite = bool(automation.get("paused")) and not pause_date
        paused_today = str(pause_date or "") == local_now.date().isoformat()
        paused = bool(indefinite or paused_today)
        return {
            "status": "paused" if paused else "active",
            "paused": paused,
            "pause_date": pause_date,
            "reason": automation.get("reason"),
            "updated_at": automation.get("updated_at"),
            "today": local_now.date().isoformat(),
            "timezone": timezone_name,
        }

    def set_parent_automation(
        self,
        action: str,
        *,
        now: str | None = None,
        timezone_name: str = "Europe/Berlin",
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Pause or resume scheduled parent-facing automation."""
        state = self._state()
        local_now = _local_datetime(now, timezone_name)
        current = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        automation = dict(current)
        if action in {"pause_today", "pause"}:
            automation.update({
                "paused": True,
                "pause_date": local_now.date().isoformat(),
                "reason": str(reason or "").strip() or None,
                "updated_at": _now(),
            })
            state["automation"] = automation
            self._write_state(state)
            return self.parent_automation_status(now=now, timezone_name=timezone_name)
        if action == "resume":
            automation.update({"paused": False, "pause_date": None, "reason": None, "updated_at": _now()})
            state["automation"] = automation
            self._write_state(state)
            return self.parent_automation_status(now=now, timezone_name=timezone_name)
        if action == "status":
            return self.parent_automation_status(now=now, timezone_name=timezone_name)
        raise ValueError(f"unsupported automation action: {action}")

    def mark_daily_parent_status(self, *, date: str, delivery_result: dict[str, Any] | None = None, status: str) -> dict[str, Any]:
        state = self._state()
        automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        daily = automation.get("daily_status") if isinstance(automation.get("daily_status"), dict) else {}
        daily.update({
            "last_status": status,
            "last_checked_date": date,
            "updated_at": _now(),
        })
        if delivery_result is not None:
            daily["last_sent_date"] = date
            daily["last_delivery"] = delivery_result
        automation["daily_status"] = daily
        state["automation"] = automation
        self._write_state(state)
        return daily

    def daily_parent_status_state(self) -> dict[str, Any]:
        state = self._state()
        automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        daily = automation.get("daily_status") if isinstance(automation.get("daily_status"), dict) else {}
        return dict(daily)

    def mark_weekly_parent_status(self, *, week_key: str, delivery_result: dict[str, Any] | None = None, status: str) -> dict[str, Any]:
        state = self._state()
        automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        weekly = automation.get("weekly_status") if isinstance(automation.get("weekly_status"), dict) else {}
        weekly.update({
            "last_status": status,
            "last_checked_week": week_key,
            "updated_at": _now(),
        })
        if delivery_result is not None:
            weekly["last_sent_week"] = week_key
            weekly["last_delivery"] = delivery_result
        automation["weekly_status"] = weekly
        state["automation"] = automation
        self._write_state(state)
        return weekly

    def weekly_parent_status_state(self) -> dict[str, Any]:
        state = self._state()
        automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
        weekly = automation.get("weekly_status") if isinstance(automation.get("weekly_status"), dict) else {}
        return dict(weekly)

    def parent_answer_status(self, *, limit: int = 3) -> dict[str, Any]:
        """Return recent answer history for parent status questions."""
        limit = max(1, min(int(limit or 3), 20))
        state = self._state()
        answers = _read_jsonl(self.paths.answers)
        recent = [self._enrich_answer_for_parent(row) for row in reversed(answers[-limit:])]
        latest = recent[0] if recent else None
        if latest is None:
            text = f"{self.agent_name}: Noch keine Antwort von {self.child_name} gespeichert."
        else:
            result_text = self._parent_result_text(latest)
            parent_candidate = latest.get("parent_delivery")
            parent_delivery = parent_candidate if isinstance(parent_candidate, dict) else {}
            delivery_status = str(parent_delivery.get("status") or "nicht protokolliert")
            text = (
                f"{self.agent_name}: {self.child_name} hat geantwortet.\n"
                f"Aufgabe: {latest.get('prompt') or 'unbekannt'}\n"
                f"Antwort: {latest.get('answer') or ''}\n"
                f"Ergebnis: {result_text}.\n"
                f"Eltern-Benachrichtigung: {delivery_status}."
            )
        return {
            "status": "ok",
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "pending": state.get("pending"),
            "queue_length": len(state.get("queue") or []),
            "answers": len(answers),
            "latest_answer": latest,
            "recent_answers": recent,
            "text": text,
        }

    def record_answer_parent_delivery(self, session_id: str | None, delivery_result: dict[str, Any]) -> dict[str, Any] | None:
        """Persist parent-notification delivery metadata on the matching answer row."""
        if not session_id:
            return None
        rows = _read_jsonl(self.paths.answers)
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if str(row.get("session_id") or "") != str(session_id):
                continue
            raw_delivery = row.get("delivery")
            delivery = raw_delivery if isinstance(raw_delivery, dict) else {}
            delivery["parent"] = {
                "status": delivery_result.get("status"),
                "adapter": delivery_result.get("adapter"),
                "target": delivery_result.get("target"),
                "message_id": delivery_result.get("message_id"),
                "error": delivery_result.get("error"),
                "attempted_at": _now(),
            }
            row["delivery"] = delivery
            rows[index] = row
            _write_jsonl(self.paths.answers, rows)
            return row
        return None

    def _enrich_answer_for_parent(self, row: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(row)
        exercise = self._exercise_by_id_or_none(str(row.get("exercise_id") or ""))
        session = self._session_by_id(str(row.get("session_id") or ""))
        if exercise:
            enriched["prompt"] = exercise.get("prompt")
            enriched["exercise"] = exercise
        elif session:
            enriched["prompt"] = session.get("prompt")
        else:
            enriched.setdefault("prompt", None)
        if session:
            enriched["session"] = session
        enriched.setdefault("max_attempts", self.max_attempts)
        raw_delivery = enriched.get("delivery")
        delivery = raw_delivery if isinstance(raw_delivery, dict) else {}
        raw_parent_delivery = delivery.get("parent")
        parent_delivery = raw_parent_delivery if isinstance(raw_parent_delivery, dict) else {"status": "not_recorded"}
        enriched["parent_delivery"] = parent_delivery
        return enriched

    def _parent_result_text(self, answer: dict[str, Any]) -> str:
        if answer.get("correct") is True:
            base = "richtig"
        elif answer.get("result") == "exhausted" or answer.get("exhausted") is True:
            base = "alle Versuche aufgebraucht"
        else:
            base = "noch nicht richtig"
        attempts = answer.get("attempts")
        max_attempts = answer.get("max_attempts") or self.max_attempts
        if attempts:
            return f"{base}, Versuch {attempts}/{max_attempts}"
        return base

    def _exercise_by_id_or_none(self, exercise_id: str) -> dict[str, Any] | None:
        if not exercise_id:
            return None
        try:
            return self._exercise_by_id(exercise_id)
        except KeyError:
            return None

    def _session_by_id(self, session_id: str) -> dict[str, Any] | None:
        if not session_id:
            return None
        state = self._state()
        pending = state.get("pending")
        if isinstance(pending, dict) and str(pending.get("id") or "") == session_id:
            return pending
        for item in state.get("queue") or []:
            if isinstance(item, dict) and str(item.get("id") or "") == session_id:
                return item
        for row in reversed(self.sessions()):
            if str(row.get("id") or "") == session_id:
                return row
        return None

    def create_parent_help_request(
        self,
        reason: str,
        *,
        subject: str | None = None,
        target: str = "parents",
        urgent: bool = False,
        requested_by: str = "child",
    ) -> dict[str, Any]:
        """Record a bounded parent-help request without external side effects."""
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            raise ValueError("help request requires reason")
        clean_subject = str(subject or "").strip() or None
        row = {
            "id": f"help-{uuid.uuid4().hex[:12]}",
            "timestamp": _now(),
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "reason": clean_reason[:800],
            "subject": clean_subject,
            "target": str(target or "parents"),
            "urgent": bool(urgent),
            "requested_by": str(requested_by or "child"),
            "status": "open",
        }
        row["text"] = self._help_request_text(row)
        _append_jsonl(self.paths.help_requests, row)
        return row

    def help_requests(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.paths.help_requests)

    def _profile(self) -> dict[str, str]:
        return {"child_id": self.child_id, "child_name": self.child_name, "agent_name": self.agent_name}

    def _help_request_text(self, request: dict[str, Any]) -> str:
        subject = request.get("subject")
        prefix = "Dringende Elternhilfe" if request.get("urgent") else "Elternhilfe"
        subject_text = f" in {subject}" if subject else ""
        return f"{self.agent_name}: {prefix} für {self.child_name}{subject_text}: {request.get('reason')}"

    def _state(self) -> dict[str, Any]:
        state = _read_json(self.paths.state, {"pending": None, "queue": [], "profile": self._profile()})
        state.setdefault("pending", None)
        state.setdefault("queue", [])
        if isinstance(state.get("pending"), dict):
            state["pending"] = _normalize_session_delivery(state["pending"])
        normalized_queue = []
        for item in state.get("queue", []):
            if isinstance(item, dict):
                normalized_queue.append(_normalize_session_delivery(item))
        state["queue"] = normalized_queue
        state["profile"] = self._profile()
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        _write_json(self.paths.state, state)

    def _choose_exercise(self, *, exercise_id: str | None = None, subject: str | None = None) -> dict[str, Any]:
        exercises = self.exercises()
        completed = self._completed_exercise_ids() if exercise_id is None else set()
        for exercise in exercises:
            if exercise_id and exercise.get("id") == exercise_id:
                return exercise
            if exercise_id is None and exercise.get("id") not in completed and (subject is None or exercise.get("subject") == subject):
                return exercise
        if exercise_id:
            raise KeyError(f"unknown exercise_id: {exercise_id}")
        raise KeyError("no matching exercise")

    def _completed_exercise_ids(self) -> set[str]:
        completed: set[str] = set()
        for row in _read_jsonl(self.paths.answers):
            if row.get("result") in {"correct", "exhausted"} or row.get("correct") is True or row.get("exhausted") is True:
                exercise_id = row.get("exercise_id")
                if exercise_id:
                    completed.add(str(exercise_id))
        return completed

    def _exercise_by_id(self, exercise_id: str) -> dict[str, Any]:
        return self._choose_exercise(exercise_id=exercise_id)

    def _make_session(
        self,
        exercise: dict[str, Any],
        *,
        mode: str,
        requested_by: str,
        timestamp: str | None = None,
        source: str | None = None,
        scheduled_id: str | None = None,
    ) -> dict[str, Any]:
        session = {
            "id": f"sess-{uuid.uuid4().hex[:12]}",
            "exercise_id": exercise["id"],
            "child_id": self.child_id,
            "child_name": self.child_name,
            "agent_name": self.agent_name,
            "subject": exercise.get("subject", "general"),
            "type": exercise.get("type", "short"),
            "prompt": exercise.get("prompt"),
            "attempts": 0,
            "delivery": _fresh_delivery_state(),
            "mode": mode,
            "requested_by": requested_by,
            "timestamp": timestamp or _now(),
        }
        if source:
            session["source"] = source
        if scheduled_id:
            session["scheduled_id"] = scheduled_id
        return session

    def _promote_next(self, state: dict[str, Any]) -> dict[str, Any] | None:
        queue = state.setdefault("queue", [])
        if not queue:
            return None
        next_session = queue.pop(0)
        next_session.pop("queued_at", None)
        next_session["timestamp"] = _now()
        next_session["attempts"] = 0
        next_session["delivery"] = _fresh_delivery_state()
        state["pending"] = next_session
        _append_jsonl(self.paths.sessions, next_session)
        return next_session
