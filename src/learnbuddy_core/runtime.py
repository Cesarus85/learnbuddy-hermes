"""Small JSON/JSONL runtime for the public LearnBuddy MVP.

This module is intentionally deterministic and filesystem-local. It is designed
for synthetic fixtures and isolated HERMES_HOME tests first; production child
profiles can be wired to it later through adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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
    def state(self) -> Path:
        return self.data_dir / "state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def status(self) -> dict[str, Any]:
        return self._state()

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

    def open_exercise(self, exercise_id: str | None = None, *, subject: str | None = None, mode: str = "manual", requested_by: str = "parent") -> dict[str, Any]:
        exercise = self._choose_exercise(exercise_id=exercise_id, subject=subject)
        state = self._state()
        session = self._make_session(exercise, mode=mode, requested_by=requested_by)
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

    def submit_answer(self, answer: Any, *, input_mode: str = "text") -> dict[str, Any]:
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
            previous_attempts=int(pending.get("attempts", 0)),
            max_attempts=self.max_attempts,
        )
        pending["attempts"] = evaluation.attempts
        result = "correct" if evaluation.correct else "exhausted" if evaluation.exhausted else "retry"
        answer_row = {
            "timestamp": _now(),
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
            "exhausted": evaluation.exhausted,
            "result": result,
            "input_mode": input_mode,
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
            "answer": answer_row,
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
        for exercise in exercises:
            if exercise_id and exercise.get("id") == exercise_id:
                return exercise
            if exercise_id is None and (subject is None or exercise.get("subject") == subject):
                return exercise
        if exercise_id:
            raise KeyError(f"unknown exercise_id: {exercise_id}")
        raise KeyError("no matching exercise")

    def _exercise_by_id(self, exercise_id: str) -> dict[str, Any]:
        return self._choose_exercise(exercise_id=exercise_id)

    def _make_session(self, exercise: dict[str, Any], *, mode: str, requested_by: str) -> dict[str, Any]:
        return {
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
            "timestamp": _now(),
        }

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
