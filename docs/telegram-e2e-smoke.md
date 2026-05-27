# Telegram E2E Smoke Runbook

This runbook documents a **controlled staging smoke** for the Telegram-first LearnBuddy alpha. It proves the full parent/child learning loop without requiring real child data or production family systems.

## Scope

The smoke covers:

1. Parent creates and sends one exercise.
2. Child receives a visible delivery result.
3. Child requests help.
4. Parent receives a bounded help request.
5. Child answers correctly.
6. Parent report includes the result.
7. `deliver-pending` repairs missing delivery metadata for an opened pending exercise.

In short: **deliver-pending repairs missing delivery metadata** and proves that queued/pending state alone is not treated as visible child delivery.

No live child or parent Telegram message is required for the default smoke. Use `delivery_mode: dry_run` and fake Telegram update transport for watcher checks. A live Telegram run is optional and must be explicit because it sends real bot messages.

## Safety rules

- Use an isolated runtime directory such as `/tmp/learnbuddy-e2e-*`.
- Use synthetic child names such as `Learner`.
- Do not use production private child-learning data.
- Do not write tokens or chat IDs into config files or logs.
- For the controlled smoke, use `delivery_mode: dry_run`.
- If testing the watcher path, provide fake `getUpdates` transport in a Python harness instead of polling real Telegram.

## Expected success marker

A successful run should end with:

```text
e2e_smoke=ok
```

and a JSON summary similar to:

```json
{
  "queue_status": "created",
  "send_status": "opened",
  "child_delivery_status": "dry_run",
  "help_status": "child_command",
  "help_command": "help",
  "help_request_count": 1,
  "answer_result": "correct",
  "report_answers": 1,
  "repair_status": "sent",
  "repair_delivery_status": "dry_run"
}
```

## Controlled local or staging harness

Run this from a checkout with LearnBuddy installed:

```bash
python - <<'PY'
import json
import os
import tempfile
from datetime import datetime, timezone

from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.delivery import DeliveryMessage, delivery_adapter_from_config
from learnbuddy_core.notifier import ParentNotifier
from learnbuddy_core.runtime import LearnBuddyRuntime
from learnbuddy_core.telegram_answer_watcher import process_child_telegram_answers

root = tempfile.mkdtemp(prefix="learnbuddy-e2e-")
config = LearnBuddyConfig(
    child_id="learner-1",
    child_name="Learner",
    agent_name="LearnBuddy",
    storage_dir=root,
    delivery_mode="dry_run",
    child_telegram_bot_token_env="E2E_CHILD_BOT",
    child_telegram_chat_id_env="E2E_CHILD_CHAT",
    parent_telegram_bot_token_env="E2E_PARENT_BOT",
    parent_telegram_chat_id_env="E2E_PARENT_CHAT",
)
for key, value in {
    "E2E_CHILD_BOT": "dummy-child-token",
    "E2E_CHILD_CHAT": "123",
    "E2E_PARENT_BOT": "dummy-parent-token",
    "E2E_PARENT_CHAT": "456",
}.items():
    os.environ[key] = value

runtime = LearnBuddyRuntime(root, child_id="learner-1", child_name="Learner", agent_name="LearnBuddy")
exercise = runtime.add_exercise({"subject": "math", "type": "short", "prompt": "2 + 2?", "answer": "4"})
opened = runtime.open_exercise(exercise["id"], mode="manual", requested_by="parent")
child_delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
    DeliveryMessage(text=opened["session"]["prompt"], metadata={"kind": "pending_exercise", "session_id": opened["session"]["id"]})
).to_dict()
runtime.mark_pending_delivery(child_delivery)

pending_ts = int(datetime.fromisoformat(opened["session"]["timestamp"]).replace(tzinfo=timezone.utc).timestamp())

def fake_transport(url, payload):
    if url.endswith("/getUpdates"):
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "message_id": 10,
                        "date": pending_ts + 1,
                        "chat": {"id": 123},
                        "from": {"is_bot": False},
                        "text": "Ich weiß nicht",
                    },
                }
            ],
        }
    raise AssertionError(url)

help_result = process_child_telegram_answers(config, state_file=f"{root}/watch.json", transport=fake_transport)
answer_result = runtime.submit_answer("4", input_mode="text")
parent_report = runtime.parent_report()
parent_notification = ParentNotifier(delivery_adapter_from_config(config, recipient="parent")).notify_report(parent_report).to_dict()

repair_exercise = runtime.add_exercise({"subject": "german", "type": "short", "prompt": "Artikel von Baum?", "answer": "der"})
repair_opened = runtime.open_exercise(repair_exercise["id"], mode="manual", requested_by="parent")
assert repair_opened["session"]["delivery"]["child"]["status"] == "not_attempted"
repair_delivery = delivery_adapter_from_config(config, recipient="child").deliver_child(
    DeliveryMessage(text=repair_opened["session"]["prompt"], metadata={"kind": "pending_exercise", "session_id": repair_opened["session"]["id"]})
).to_dict()
runtime.mark_pending_delivery(repair_delivery)

summary = {
    "queue_status": "created",
    "send_status": opened["status"],
    "child_delivery_status": child_delivery["status"],
    "help_status": help_result["status"],
    "help_command": help_result["command"],
    "help_request_count": len(runtime.help_requests()),
    "answer_result": answer_result["result"],
    "report_answers": parent_report["answers"],
    "parent_report_delivery_status": parent_notification["status"],
    "repair_status": "sent",
    "repair_delivery_status": repair_delivery["status"],
}
assert summary["child_delivery_status"] == "dry_run"
assert summary["help_status"] == "child_command"
assert summary["help_command"] == "help"
assert summary["help_request_count"] == 1
assert summary["answer_result"] == "correct"
assert summary["parent_report_delivery_status"] == "dry_run"
assert summary["repair_delivery_status"] == "dry_run"
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("e2e_smoke=ok")
PY
```

## Optional live Telegram smoke

Only run this when you intentionally want real bot messages to the configured child/parent chats:

1. Use the staging Telegram config plus env file.
2. Send exactly one synthetic exercise.
3. Confirm the child-bot message is visible.
4. Reply with a synthetic child message such as `Ich weiß nicht`.
5. Run `learnbuddy watch-telegram-answers` once.
6. Confirm child acknowledgement and parent-help notification.
7. Answer the pending task and send a parent report.
8. Clean up any test pending item before leaving the staging host.

Live smoke is intentionally not the default because a good public-alpha runbook should be repeatable in CI-like staging without pinging real humans.
