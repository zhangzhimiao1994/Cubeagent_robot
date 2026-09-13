#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=/etc/cube-robot/robot.toml
STATE_DIR=/var/lib/cube-robot
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="${RUNTIME_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-}"
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

if [[ -z "$PYTHON_BIN" ]]; then
  if "$DRY_RUN"; then
    if [[ -x "$RUNTIME_ROOT/.venv/bin/python" ]]; then
      PYTHON_BIN="$RUNTIME_ROOT/.venv/bin/python"
    elif [[ -x "/usr/local/lib/cube-robot/.venv/bin/python" ]]; then
      PYTHON_BIN="/usr/local/lib/cube-robot/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN=python3
    else
      PYTHON_BIN=python
    fi
  else
    for candidate in \
      "$RUNTIME_ROOT/.venv/bin/python" \
      "/usr/local/lib/cube-robot/.venv/bin/python" \
      "$STATE_DIR/current/bin/python" \
      python3 \
      python
    do
      if [[ "$candidate" == */* ]]; then
        if [[ -x "$candidate" ]]; then
          PYTHON_BIN="$candidate"
          break
        fi
      elif command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
      fi
    done
    if [[ -z "$PYTHON_BIN" ]]; then
      printf 'could not find a Python runtime for cube-robot OTA\n' >&2
      exit 1
    fi
  fi
fi

arguments=(--config "$CONFIG_PATH" --state-dir "$STATE_DIR")
if "$DRY_RUN"; then
  arguments+=(--dry-run)
fi
export PYTHONPATH="$RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m cube_robot_runtime.ota.updater "${arguments[@]}"
