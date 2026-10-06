#!/usr/bin/env bash
# Run only after Niri publishes its actual Wayland environment.
set -euo pipefail

if [[ -z "${NIRI_SOCKET:-}" || -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "skwd-session: a running Niri session is required" >&2
    exit 1
fi

exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/../personal/desktop-session.py" start niri
