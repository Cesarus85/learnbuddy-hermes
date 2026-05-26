import importlib.util
import json
from pathlib import Path


def load_plugin():
    path = Path("plugins/learnbuddy-learning/__init__.py")
    spec = importlib.util.spec_from_file_location("learnbuddy_learning_plugin", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plugin_tools_use_isolated_data_dir_and_return_json(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "plugin-data"

    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "data_dir": str(data_dir),
        "subject": "math",
        "prompt": "1 + 1?",
        "answer": "2",
    }))
    opened = json.loads(plugin.learnbuddy_next_exercise({"data_dir": str(data_dir), "exercise_id": queued["exercise"]["id"]}))
    answer = json.loads(plugin.learnbuddy_submit_answer({"data_dir": str(data_dir), "answer": "2"}))
    status = json.loads(plugin.learnbuddy_learning_status({"data_dir": str(data_dir)}))

    assert opened["status"] == "opened"
    assert answer["result"] == "correct"
    assert status["pending"] is None
    assert (data_dir / "exercises.jsonl").exists()
    assert (data_dir / "answers.jsonl").exists()


def test_plugin_accepts_config_file_for_child_and_agent_identity(tmp_path):
    plugin = load_plugin()
    data_dir = tmp_path / "configured-data"
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        f"""
child:
  id: kid-2
  display_name: Jamie
agent:
  name: LernKumpel
safety:
  max_attempts: 2
storage:
  data_dir: {data_dir}
""".strip(),
        encoding="utf-8",
    )

    queued = json.loads(plugin.learnbuddy_queue_exercise({
        "config_path": str(config_path),
        "subject": "english",
        "prompt": "Translate: Katze",
        "answer": "cat",
    }))
    opened = json.loads(plugin.learnbuddy_next_exercise({"config_path": str(config_path), "exercise_id": queued["exercise"]["id"]}))
    first_wrong = json.loads(plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "dog"}))
    exhausted = json.loads(plugin.learnbuddy_submit_answer({"config_path": str(config_path), "answer": "mouse"}))
    report = json.loads(plugin.learnbuddy_parent_report({"config_path": str(config_path)}))

    assert opened["session"]["child_id"] == "kid-2"
    assert opened["session"]["child_name"] == "Jamie"
    assert opened["session"]["agent_name"] == "LernKumpel"
    assert first_wrong["result"] == "retry"
    assert exhausted["result"] == "exhausted"
    assert exhausted["max_attempts"] == 2
    assert report["child_name"] == "Jamie"
    assert report["agent_name"] == "LernKumpel"
