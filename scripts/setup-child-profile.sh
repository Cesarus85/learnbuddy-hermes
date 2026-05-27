#!/usr/bin/env bash
set -euo pipefail

PROFILE="learnbuddy-child"
CONFIG_PATH=""
ENV_FILE=""
MODEL_PROVIDER=""
MODEL_NAME=""
CAPABILITY_LEVEL="guided"
SKIP_INSTALL="0"

usage() {
  cat <<'USAGE'
Usage: scripts/setup-child-profile.sh [options]

Create or update a dedicated locked-down Hermes child profile for LearnBuddy.
Run from the learnbuddy-hermes repository root after Hermes is installed.

Options:
  --profile NAME        Child Hermes profile name (default: learnbuddy-child)
  --config PATH         LearnBuddy YAML path to expose as LEARNBUDDY_CONFIG_PATH
  --env-file PATH       Optional env file path to expose as LEARNBUDDY_ENV_FILE
  --capability-level LEVEL
                       Child capability preset: locked|guided|curious|teen-supervised
  --provider PROVIDER   Optional model provider for the child profile
  --model MODEL         Optional model name for the child profile
  --skip-install        Do not run 'python -m pip install -e .'
  -h, --help            Show this help

The script writes a child-profile `SOUL.md` that routes short numeric/text answers through `learnbuddy_child_submit_answer` before free chat. Existing Telegram sessions may keep an older prompt; after changing the SOUL, restart the child gateway and start a fresh session if needed.

The script does NOT write Telegram tokens or chat IDs. Put real secrets in the
env file yourself and keep it mode 600. If your PATH has python3 but not python,
the script auto-detects it; set PYTHON_BIN=/path/to/python for unusual systems.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?missing profile}"; shift 2 ;;
    --config) CONFIG_PATH="${2:?missing config path}"; shift 2 ;;
    --env-file) ENV_FILE="${2:?missing env file path}"; shift 2 ;;
    --capability-level) CAPABILITY_LEVEL="${2:?missing capability level}"; shift 2 ;;
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

BASE_FORBIDDEN_TOOLSETS='["terminal","file","code_execution","web","browser","computer_use","messaging","homeassistant","kanban","memory","todo","session_search","image_gen"]'
case "$CAPABILITY_LEVEL" in
  locked)
    TELEGRAM_TOOLSETS='["learnbuddy_child"]'
    DISABLED_TOOLSETS='["terminal","file","code_execution","web","browser","computer_use","messaging","homeassistant","kanban","memory","todo","session_search","image_gen","tts","vision","search","skills","delegation","cronjob"]'
    ;;
  guided)
    TELEGRAM_TOOLSETS='["learnbuddy_child","tts","vision"]'
    DISABLED_TOOLSETS='["terminal","file","code_execution","web","browser","computer_use","messaging","homeassistant","kanban","memory","todo","session_search","image_gen","search","skills","delegation","cronjob"]'
    ;;
  curious)
    TELEGRAM_TOOLSETS='["learnbuddy_child","tts","vision","search"]'
    DISABLED_TOOLSETS='["terminal","file","code_execution","web","browser","computer_use","messaging","homeassistant","kanban","memory","todo","session_search","image_gen","skills","delegation","cronjob"]'
    ;;
  teen-supervised)
    TELEGRAM_TOOLSETS='["learnbuddy_child","tts","vision","search","skills","delegation","cronjob"]'
    DISABLED_TOOLSETS="$BASE_FORBIDDEN_TOOLSETS"
    ;;
  *)
    echo "Invalid --capability-level: $CAPABILITY_LEVEL" >&2
    echo "Expected one of: locked|guided|curious|teen-supervised" >&2
    exit 2
    ;;
esac

if [[ "$SKIP_INSTALL" != "1" ]]; then
  "$PYTHON_BIN" -m pip install -e .
fi

if ! hermes profile list 2>/dev/null | grep -Eq "(^|[[:space:]])${PROFILE}([[:space:]]|$)"; then
  hermes profile create "$PROFILE" --no-skills --no-alias
fi

PROFILE_HOME="$HOME/.hermes/profiles/$PROFILE"
PLUGIN_DIR="$PROFILE_HOME/plugins/learnbuddy-learning"
mkdir -p "$PLUGIN_DIR"
rsync -a --delete plugins/learnbuddy-learning/ "$PLUGIN_DIR/"
cp templates/child-profile/SOUL.md "$PROFILE_HOME/SOUL.md"

hermes --profile "$PROFILE" plugins enable learnbuddy-learning || true

PROFILE_CONFIG="$PROFILE_HOME/config.yaml"
"$PYTHON_BIN" - "$PROFILE_CONFIG" "$TELEGRAM_TOOLSETS" "$DISABLED_TOOLSETS" <<'PY'
from pathlib import Path
import json
import sys
import yaml

path = Path(sys.argv[1])
toolsets = json.loads(sys.argv[2])
disabled_toolsets = json.loads(sys.argv[3])
config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
if not isinstance(config, dict):
    config = {}
platform_toolsets = config.setdefault("platform_toolsets", {})
if not isinstance(platform_toolsets, dict):
    platform_toolsets = {}
    config["platform_toolsets"] = platform_toolsets
platform_toolsets["telegram"] = toolsets
known_plugin_toolsets = config.setdefault("known_plugin_toolsets", {})
if not isinstance(known_plugin_toolsets, dict):
    known_plugin_toolsets = {}
    config["known_plugin_toolsets"] = known_plugin_toolsets
known_plugin_toolsets["telegram"] = ["learnbuddy_child", "learnbuddy_learning"]
agent = config.setdefault("agent", {})
if not isinstance(agent, dict):
    agent = {}
    config["agent"] = agent
agent["disabled_toolsets"] = disabled_toolsets
path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
PY

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

echo "LearnBuddy child profile ready: $PROFILE"
echo "Capability level: $CAPABILITY_LEVEL"
echo "Enabled Telegram toolsets: $TELEGRAM_TOOLSETS"
echo "Forbidden by design: terminal, file, code_execution, homeassistant, generic messaging"
echo "Expected child gateway service: hermes-gateway-${PROFILE}.service"
echo "Start or restart the profile gateway only after you configured a dedicated child Telegram bot."
