#!/usr/bin/env bash
set -euo pipefail

PROFILE="default"
CONFIG_PATH=""
ENV_FILE=""
ON_BOOT_SEC="2min"
ON_UNIT_ACTIVE_SEC="5min"
PYTHON_BIN="${PYTHON_BIN:-}"
START_NOW=0
ENABLE=0

usage() {
  cat <<'USAGE'
Usage: scripts/install-dispatch-timer.sh [options]

Install a systemd --user timer that runs one public-safe LearnBuddy dispatcher tick.

Options:
  --profile PROFILE             Hermes/profile label for unit names (default: default)
  --config PATH                 LearnBuddy YAML path (recommended)
  --env-file PATH               Optional KEY=VALUE env file for Telegram delivery secrets
  --on-boot-sec SPEC            systemd OnBootSec spec (default: 2min)
  --on-unit-active-sec SPEC     systemd OnUnitActiveSec spec (default: 5min)
  --enable                      Enable the timer
  --start                       Start the timer after writing units
  --python PATH                 Python binary override for learnbuddy CLI execution
  -h, --help                    Show this help

The service uses: learnbuddy dispatch-plan
It picks up due scheduled exercises, opens at most one exercise, delivers it to the child adapter,
and exits. It is separate from the daily-status reporter timer.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --config) CONFIG_PATH="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --on-boot-sec) ON_BOOT_SEC="$2"; shift 2 ;;
    --on-unit-active-sec) ON_UNIT_ACTIVE_SEC="$2"; shift 2 ;;
    --enable) ENABLE=1; shift ;;
    --start) START_NOW=1; shift ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  # Prefer a local project virtualenv when the installer is run from a source checkout.
  # This keeps systemd services on staging/VPS installs from accidentally using
  # /usr/bin/python3 without the editable LearnBuddy package installed.
  if [[ -x "${PWD}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PWD}/.venv/bin/python"
  elif [[ -x "$(dirname "${PWD}")/.venv/bin/python" ]]; then
    PYTHON_BIN="$(dirname "${PWD}")/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "No python3/python found. Pass --python /path/to/python." >&2
    exit 1
  fi
fi

UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
SERVICE_NAME="learnbuddy-dispatch-${PROFILE}.service"
TIMER_NAME="learnbuddy-dispatch-${PROFILE}.timer"
SERVICE_PATH="${UNIT_DIR}/${SERVICE_NAME}"
TIMER_PATH="${UNIT_DIR}/${TIMER_NAME}"

ENV_LINES=("Environment=PYTHONUNBUFFERED=1")
if [[ -n "$CONFIG_PATH" ]]; then
  ENV_LINES+=("Environment=LEARNBUDDY_CONFIG_PATH=${CONFIG_PATH}")
fi
if [[ -n "$ENV_FILE" ]]; then
  ENV_LINES+=("Environment=LEARNBUDDY_ENV_FILE=${ENV_FILE}")
  ENV_LINES+=("EnvironmentFile=${ENV_FILE}")
fi

EXEC_ARGS=("dispatch-plan")
if [[ -n "$CONFIG_PATH" ]]; then
  EXEC_ARGS+=("--config" "${CONFIG_PATH}")
fi

{
  echo "[Unit]"
  echo "Description=LearnBuddy scheduled exercise dispatcher (${PROFILE})"
  echo
  echo "[Service]"
  echo "Type=oneshot"
  for line in "${ENV_LINES[@]}"; do
    echo "$line"
  done
  printf "ExecStart=%s -m learnbuddy_core.cli" "$PYTHON_BIN"
  for arg in "${EXEC_ARGS[@]}"; do
    printf " %s" "$arg"
  done
  printf "\n"
} > "$SERVICE_PATH"

cat > "$TIMER_PATH" <<TIMER
[Unit]
Description=Run LearnBuddy scheduled exercise dispatcher (${PROFILE})

[Timer]
OnBootSec=${ON_BOOT_SEC}
OnUnitActiveSec=${ON_UNIT_ACTIVE_SEC}
Persistent=true

[Install]
WantedBy=timers.target
TIMER

systemctl --user daemon-reload

if [[ "$ENABLE" -eq 1 ]]; then
  systemctl --user enable "$TIMER_NAME"
fi
if [[ "$START_NOW" -eq 1 ]]; then
  systemctl --user start "$TIMER_NAME"
fi

echo "installed_service=${SERVICE_PATH}"
echo "installed_timer=${TIMER_PATH}"
echo "timer_name=${TIMER_NAME}"
echo "on_boot_sec=${ON_BOOT_SEC}"
echo "on_unit_active_sec=${ON_UNIT_ACTIVE_SEC}"
echo "enabled=${ENABLE}"
echo "started=${START_NOW}"
