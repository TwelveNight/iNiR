#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${INIR_VENV:-}" ]]; then
    _ii_venv="$(eval echo "$INIR_VENV")"
else
    _ii_venv="${INIR_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/inir}/.venv"
fi
source "$_ii_venv/bin/activate" 2>/dev/null || true
"$_ii_venv/bin/python3" "$SCRIPT_DIR/find_regions.py" "$@"
deactivate 2>/dev/null || true
