#!/usr/bin/env bash
set -euo pipefail

PROFILE="learnbuddy-child"
CONFIG_PATH=""
ENV_FILE=""
MODEL_PROVIDER=""
MODEL_NAME=""
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
  --provider PROVIDER   Optional model provider for the child profile
  --model MODEL         Optional model name for the child profile
  --skip-install        Do not run 'python -m pip install -e .'
  -h, --help            Show this help

The script does NOT write Telegram tokens or chat IDs. Put real secrets in the
env file yourself and keep it mode 600.
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

if [[ "$SKIP_INSTALL" != "1" ]]; then
  python -m pip install -e .
fi

if ! hermes profile list 2>/dev/null | grep -Eq "(^|[[:space:]])${PROFILE}([[:space:]]|$)"; then
  hermes profile create "$PROFILE" --no-skills --no-alias
fi

PROFILE_HOME="$HOME/.hermes/profiles/$PROFILE"
PLUGIN_DIR="$PROFILE_HOME/plugins/learnbuddy-learning"
mkdir -p "$PLUGIN_DIR"
rsync -a --delete plugins/learnbuddy-learning/ "$PLUGIN_DIR/"

hermes --profile "$PROFILE" plugins enable learnbuddy-learning || true
hermes --profile "$PROFILE" config set platform_toolsets.telegram '["learnbuddy_child","tts","vision"]'

if [[ -n "$MODEL_PROVIDER" ]]; then
  hermes --profile "$PROFILE" config set model.provider "$MODEL_PROVIDER"
fi
if [[ -n "$MODEL_NAME" ]]; then
  hermes --profile "$PROFILE" config set model.default "$MODEL_NAME"
fi

PROFILE_ENV="$PROFILE_HOME/.env"
touch "$PROFILE_ENV"
chmod 600 "$PROFILE_ENV"
python - "$PROFILE_ENV" "$CONFIG_PATH" "$ENV_FILE" <<'PY'
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
echo "Enabled Telegram toolsets: learnbuddy_child, tts, vision"
echo "Forbidden by design: terminal, file, code_execution, homeassistant, generic messaging"
echo "Start or restart the profile gateway only after you configured a dedicated child Telegram bot."
