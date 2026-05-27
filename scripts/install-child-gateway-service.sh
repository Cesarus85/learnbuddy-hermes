#!/usr/bin/env bash
set -euo pipefail

PROFILE="learnbuddy-child"
SERVICE_NAME=""
START_SERVICE="0"
ENABLE_SERVICE="0"
FORCE="0"

usage() {
  cat <<'USAGE'
Usage: scripts/install-child-gateway-service.sh [options]

Install a dedicated systemd user service for the LearnBuddy child Hermes gateway.
Run this after scripts/setup-child-profile.sh and only start it after a dedicated
child Telegram bot token and allowlists are present in the child profile env.

Options:
  --profile NAME        Child Hermes profile name (default: learnbuddy-child)
  --service-name NAME   systemd user service name without .service
                        (default: hermes-gateway-<profile>)
  --enable              Enable the service for user login/boot
  --start               Start/restart the service now (also validates Telegram guardrails)
  --force               Allow start even if TELEGRAM_FREE_RESPONSE_CHATS is absent
  -h, --help            Show this help

Safety guardrails before --start/--enable:
  - profile .env must contain TELEGRAM_BOT_TOKEN
  - profile .env must contain TELEGRAM_ALLOWED_USERS or TELEGRAM_ALLOWED_CHATS
  - profile .env must contain TELEGRAM_HOME_CHANNEL
  - profile .env should contain TELEGRAM_FREE_RESPONSE_CHATS unless --force is used
  - child token must not match ~/.hermes/.env TELEGRAM_BOT_TOKEN when present

The script never prints token or chat ID values.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?missing profile}"; shift 2 ;;
    --service-name) SERVICE_NAME="${2:?missing service name}"; shift 2 ;;
    --enable) ENABLE_SERVICE="1"; shift ;;
    --start) START_SERVICE="1"; shift ;;
    --force) FORCE="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! "$PROFILE" =~ ^[A-Za-z0-9_.@-]+$ ]]; then
  echo "Invalid profile name: $PROFILE" >&2
  exit 2
fi

if [[ -z "$SERVICE_NAME" ]]; then
  SERVICE_NAME="hermes-gateway-${PROFILE}"
fi
if [[ ! "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]]; then
  echo "Invalid service name: $SERVICE_NAME" >&2
  exit 2
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes CLI not found in PATH. Install Hermes first." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found; this installer targets Linux systemd user services." >&2
  exit 1
fi

PROFILE_HOME="$HOME/.hermes/profiles/$PROFILE"
PROFILE_ENV="$PROFILE_HOME/.env"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_PATH="$UNIT_DIR/${SERVICE_NAME}.service"
LOG_DIR="$HOME/.hermes/logs"
HERMES_BIN="$(command -v hermes)"
if command -v readlink >/dev/null 2>&1; then
  HERMES_BIN="$(readlink -f "$HERMES_BIN" 2>/dev/null || printf '%s' "$HERMES_BIN")"
fi

if [[ ! -d "$PROFILE_HOME" ]]; then
  echo "Profile home not found: $PROFILE_HOME" >&2
  echo "Run scripts/setup-child-profile.sh --profile $PROFILE first." >&2
  exit 1
fi

get_env_value() {
  local file="$1"
  local key="$2"
  [[ -f "$file" ]] || return 1
  python - "$file" "$key" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k.strip() == key:
        print(v.strip().strip('"').strip("'"))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

require_profile_gateway_ready() {
  local child_token default_token
  child_token="$(get_env_value "$PROFILE_ENV" TELEGRAM_BOT_TOKEN || true)"
  if [[ -z "$child_token" ]]; then
    echo "Refusing to start/enable: $PROFILE_ENV has no TELEGRAM_BOT_TOKEN." >&2
    echo "Use a dedicated child BotFather token in the child profile env; do not reuse the parent/default bot." >&2
    exit 1
  fi

  if [[ -z "$(get_env_value "$PROFILE_ENV" TELEGRAM_ALLOWED_USERS || true)" && -z "$(get_env_value "$PROFILE_ENV" TELEGRAM_ALLOWED_CHATS || true)" ]]; then
    echo "Refusing to start/enable: set TELEGRAM_ALLOWED_USERS or TELEGRAM_ALLOWED_CHATS in $PROFILE_ENV." >&2
    exit 1
  fi

  if [[ -z "$(get_env_value "$PROFILE_ENV" TELEGRAM_HOME_CHANNEL || true)" ]]; then
    echo "Refusing to start/enable: set TELEGRAM_HOME_CHANNEL in $PROFILE_ENV." >&2
    exit 1
  fi

  if [[ "$FORCE" != "1" && -z "$(get_env_value "$PROFILE_ENV" TELEGRAM_FREE_RESPONSE_CHATS || true)" ]]; then
    echo "Refusing to start/enable: set TELEGRAM_FREE_RESPONSE_CHATS for direct child chat, or pass --force for install-specific exceptions." >&2
    exit 1
  fi

  default_token="$(get_env_value "$HOME/.hermes/.env" TELEGRAM_BOT_TOKEN || true)"
  if [[ -n "$default_token" && "$child_token" == "$default_token" ]]; then
    echo "Refusing to start/enable: child profile TELEGRAM_BOT_TOKEN matches the default profile token." >&2
    echo "Child and parent/default gateways must use separate Telegram bots." >&2
    exit 1
  fi
}

mkdir -p "$UNIT_DIR" "$LOG_DIR"
cat > "$UNIT_PATH" <<UNIT
[Unit]
Description=Hermes Gateway (${PROFILE} LearnBuddy child profile)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h
Environment=HOME=%h
Environment=PATH=%h/.local/bin:%h/.hermes/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${HERMES_BIN} --profile ${PROFILE} gateway run
Restart=on-failure
RestartSec=10
StandardOutput=append:%h/.hermes/logs/${SERVICE_NAME}.log
StandardError=append:%h/.hermes/logs/${SERVICE_NAME}.log

[Install]
WantedBy=default.target
UNIT
chmod 600 "$UNIT_PATH"

systemctl --user daemon-reload

if [[ "$ENABLE_SERVICE" == "1" || "$START_SERVICE" == "1" ]]; then
  require_profile_gateway_ready
fi

if [[ "$ENABLE_SERVICE" == "1" ]]; then
  systemctl --user enable "${SERVICE_NAME}.service"
fi

if [[ "$START_SERVICE" == "1" ]]; then
  systemctl --user restart "${SERVICE_NAME}.service"
  sleep 2
  systemctl --user --no-pager --lines=20 status "${SERVICE_NAME}.service"
fi

echo "Installed child gateway service: ${SERVICE_NAME}.service"
echo "Unit path: $UNIT_PATH"
echo "Profile: $PROFILE"
echo "Start command: systemctl --user restart ${SERVICE_NAME}.service"
echo "Status command: systemctl --user status ${SERVICE_NAME}.service"
echo "Log file: $HOME/.hermes/logs/${SERVICE_NAME}.log"
