#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR=/etc/cube-robot
STATE_DIR=/var/lib/cube-robot
CONFIG_PATH="$CONFIG_DIR/robot.toml"
DEVICE_ID_PATH="$CONFIG_DIR/device-id"
DRY_RUN=false

usage() { printf 'Usage: %s [--dry-run] [--config PATH]\n' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
    --config)
      CONFIG_PATH="${2:?missing value for --config}"
      CONFIG_DIR="$(dirname "$CONFIG_PATH")"
      DEVICE_ID_PATH="$CONFIG_DIR/device-id"
      shift
      ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

if "$DRY_RUN"; then
  printf 'dry-run: would create %s and %s\n' "$CONFIG_DIR" "$STATE_DIR"
  printf 'dry-run: would create device identity at %s\n' "$DEVICE_ID_PATH"
  printf 'dry-run: would install config at %s\n' "$CONFIG_PATH"
  exit 0
fi

install -d -m 0750 -o cube-robot -g cube-robot "$CONFIG_DIR" "$STATE_DIR"
if [[ ! -f "$DEVICE_ID_PATH" ]]; then
  umask 0077
  od -An -N10 -tx1 /dev/urandom | tr -d ' \n' >"$DEVICE_ID_PATH"
  printf '\n' >> "$DEVICE_ID_PATH"
  chown cube-robot:cube-robot "$DEVICE_ID_PATH"
fi
if [[ ! -f "$CONFIG_PATH" ]]; then
  install -m 0640 -o cube-robot -g cube-robot "$(dirname "$0")/../config/robot.toml.example" "$CONFIG_PATH"
fi
