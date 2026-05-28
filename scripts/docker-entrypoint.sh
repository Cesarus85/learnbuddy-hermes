#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${LEARNBUDDY_CONFIG_PATH:-/app/config/learnbuddy.yaml}"
DATA_DIR="${LEARNBUDDY_DATA_DIR:-/app/data}"
CHILD_ID="${LEARNBUDDY_CHILD_ID:-learner}"
CHILD_NAME="${LEARNBUDDY_CHILD_NAME:-Learner}"
AGENT_NAME="${LEARNBUDDY_AGENT_NAME:-LearnBuddy}"

if [ ! -f "$CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$CONFIG_PATH")" "$DATA_DIR"
  learnbuddy setup \
    --config "$CONFIG_PATH" \
    --data-dir "$DATA_DIR" \
    --child-id "$CHILD_ID" \
    --child-name "$CHILD_NAME" \
    --agent-name "$AGENT_NAME" \
    --delivery-mode dry_run
fi

if [ "$#" -eq 0 ]; then
  exec learnbuddy doctor --config "$CONFIG_PATH"
fi

case "$1" in
  sh|bash|python|python3|/bin/*|/usr/bin/*)
    exec "$@"
    ;;
  *)
    exec learnbuddy "$@"
    ;;
esac
