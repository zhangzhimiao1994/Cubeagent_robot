#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=/etc/cube-robot/robot.toml
STATE_DIR=/var/lib/cube-robot
DRY_RUN=false

usage() { printf 'Usage: %s [--dry-run] [--config PATH] [--state-dir PATH]\n' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
    --config) CONFIG_PATH="${2:?missing value for --config}"; shift ;;
    --state-dir) STATE_DIR="${2:?missing value for --state-dir}"; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

RUNTIME_PYTHON="${CUBE_ROBOT_PYTHON:-$STATE_DIR/current/bin/python}"
arguments=(--config "$CONFIG_PATH" --state-dir "$STATE_DIR")
if "$DRY_RUN"; then
  arguments+=(--dry-run)
fi
exec "$RUNTIME_PYTHON" -m cube_robot_runtime.ota.updater "${arguments[@]}"
