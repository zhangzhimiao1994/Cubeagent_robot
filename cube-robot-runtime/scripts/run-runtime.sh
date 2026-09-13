#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="${RUNTIME_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
STATE_DIR="${STATE_DIR:-/var/lib/cube-robot}"
BOOTSTRAP_ROOT="${BOOTSTRAP_ROOT:-/usr/local/lib/cube-robot}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in \
    "$RUNTIME_ROOT/.venv/bin/python" \
    "$BOOTSTRAP_ROOT/.venv/bin/python" \
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
fi

if [[ -z "$PYTHON_BIN" ]]; then
  printf 'could not find a Python runtime for cube-robot\n' >&2
  exit 1
fi

export PYTHONPATH="$RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m cube_robot_runtime.main "$@"
