#!/usr/bin/env bash
set -euo pipefail

PROFILE="learnbuddy-parent"
CONFIG_PATH=""
ENV_FILE=""
MODEL_PROVIDER=""
MODEL_NAME=""
SKIP_INSTALL="0"

usage() {
  cat <<'USAGE'
Usage: scripts/setup-parent-profile.sh [options]

Create or update a parent-facing Hermes profile for LearnBuddy Telegram commands.
Run from the learnbuddy-hermes repository root after Hermes is installed.

Options:
  --profile NAME       Parent Hermes profile name (default: learnbuddy-parent)
  --config PATH        LearnBuddy YAML path to expose as LEARNBUDDY_CONFIG_PATH
  --env-file PATH      Optional env file path to expose as LEARNBUDDY_ENV_FILE
  --provider PROVIDER  Optional model provider for the parent profile
  --model MODEL        Optional model name for the parent profile
  --skip-install       Do not run 'python -m pip install -e .'
  -h, --help           Show this help

The script writes templates/parent-profile/SOUL.md so the parent gateway routes
Telegram commands through learnbuddy_parent_command_contracts and never exposes
learnbuddy_child. It does NOT write Telegram tokens or chat IDs. Put real secrets
in the env file yourself and keep it mode 600. If your PATH has python3 but not
python, the script auto-detects it; set PYTHON_BIN=/path/to/python for unusual systems.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?missing profile}"; shift 2 ;;
    --config) CONFIG_PATH="${2:?missing config path}"; shift 2 ;;
    --env-file) ENV_FILE="${2:?missing env file path}"; shift 2 ;;
    --provider) MODEL_PROVIDER="${2:?missing provider}"; shift 2 ;;
    --model) MODEL_NAME="${2:?missing model}"; shift 2 ;;
    --skip-install) SKIP_INSTALL="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -f plugins/learnbuddy-learning/plugin.yaml ]]; then
  echo "Run this script from the learnbuddy-hermes repository root." >&2
  exit 1
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes CLI not found in PATH. Install Hermes first." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "No python3/python executable found in PATH. Set PYTHON_BIN=/path/to/python." >&2
    exit 1
  fi
fi

if [[ "$SKIP_INSTALL" != "1" ]]; then
  "$PYTHON_BIN" -m pip install -e .
fi

if [[ "$PROFILE" != "default" ]] && ! hermes profile list 2>/dev/null | grep -Eq "(^|[[:space:]])${PROFILE}([[:space:]]|$)"; then
  hermes profile create "$PROFILE" --no-skills --no-alias
fi

if [[ "$PROFILE" == "default" ]]; then
  PROFILE_HOME="$HOME/.hermes"
else
  PROFILE_HOME="$HOME/.hermes/profiles/$PROFILE"
fi
PLUGIN_DIR="$PROFILE_HOME/plugins/learnbuddy-learning"
mkdir -p "$PLUGIN_DIR"
rsync -a --delete plugins/learnbuddy-learning/ "$PLUGIN_DIR/"
cp templates/parent-profile/SOUL.md "$PROFILE_HOME/SOUL.md"

hermes --profile "$PROFILE" plugins enable learnbuddy-learning || true

PROFILE_CONFIG="$PROFILE_HOME/config.yaml"
"$PYTHON_BIN" - "$PROFILE_CONFIG" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
if not isinstance(config, dict):
    config = {}
platform_toolsets = config.setdefault("platform_toolsets", {})
if not isinstance(platform_toolsets, dict):
    platform_toolsets = {}
    config["platform_toolsets"] = platform_toolsets
platform_toolsets["telegram"] = ["learnbuddy_learning"]
known_plugin_toolsets = config.setdefault("known_plugin_toolsets", {})
if not isinstance(known_plugin_toolsets, dict):
    known_plugin_toolsets = {}
    config["known_plugin_toolsets"] = known_plugin_toolsets
known_plugin_toolsets["telegram"] = ["learnbuddy_learning", "learnbuddy_child"]
agent = config.setdefault("agent", {})
if not isinstance(agent, dict):
    agent = {}
    config["agent"] = agent
disabled = agent.get("disabled_toolsets", [])
if not isinstance(disabled, list):
    disabled = []
if "learnbuddy_child" not in disabled:
    disabled.append("learnbuddy_child")
agent["disabled_toolsets"] = disabled
path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
PY

copy_default_model_config_if_needed() {
  "$PYTHON_BIN" - "$HOME/.hermes/config.yaml" "$PROFILE_CONFIG" <<'PY'
from pathlib import Path
import sys
import yaml

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
if not source_path.exists() or not target_path.exists():
    raise SystemExit(0)
source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
target = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
if not isinstance(source, dict) or not isinstance(target, dict):
    raise SystemExit(0)
current = target.get("model")
current_ready = isinstance(current, dict) and bool(current.get("provider")) and bool(current.get("default"))
if current_ready:
    raise SystemExit(0)
source_model = source.get("model")
if not isinstance(source_model, dict) or not source_model.get("provider") or not source_model.get("default"):
    print("Warning: parent profile has no model and default profile has no complete model; pass --provider and --model before starting the parent gateway.", file=sys.stderr)
    raise SystemExit(0)
allowed = {"provider", "default", "base_url", "context_length", "max_tokens"}
target["model"] = {key: value for key, value in source_model.items() if key in allowed and value not in (None, "")}
target_path.write_text(yaml.safe_dump(target, sort_keys=False, allow_unicode=True), encoding="utf-8")
print("Copied non-secret default model settings into parent profile config.")
PY
}

copy_default_model_config_if_needed

if [[ -n "$MODEL_PROVIDER" ]]; then
  hermes --profile "$PROFILE" config set model.provider "$MODEL_PROVIDER"
fi
if [[ -n "$MODEL_NAME" ]]; then
  hermes --profile "$PROFILE" config set model.default "$MODEL_NAME"
fi

PROFILE_ENV="$PROFILE_HOME/.env"
touch "$PROFILE_ENV"
chmod 600 "$PROFILE_ENV"
"$PYTHON_BIN" - "$PROFILE_ENV" "$CONFIG_PATH" "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
config_path = sys.argv[2]
env_file = sys.argv[3]
updates = {}
if config_path:
    updates["LEARNBUDDY_CONFIG_PATH"] = str(Path(config_path).expanduser().resolve())
if env_file:
    updates["LEARNBUDDY_ENV_FILE"] = str(Path(env_file).expanduser().resolve())
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
kept = [line for line in lines if not any(line.startswith(f"{key}=") for key in updates)]
for key, value in updates.items():
    kept.append(f"{key}={value}")
path.write_text("\n".join(kept).rstrip() + ("\n" if kept else ""), encoding="utf-8")
PY

hermes --profile "$PROFILE" config check

echo "LearnBuddy parent profile ready: $PROFILE"
echo 'Enabled Telegram toolsets: ["learnbuddy_learning"]'
echo "Blocked from parent Telegram: learnbuddy_child"
echo "Restart the parent gateway after changing SOUL/config."
