#!/usr/bin/env bash
# Read-only host checks. No package installation or live configuration writes.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
# Automation/TTY shells may omit these; only connect to this user's existing bus.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "$XDG_RUNTIME_DIR/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi
failed=0
python3 "$repo/scripts/personal/dependencies.py" || failed=1
if command -v niri >/dev/null; then
    niri validate --config "$repo/defaults/niri/config.kdl" || failed=1
fi
if [[ ! -x "$config_home/quickshell/ii/scripts/colors/skwd-wall-theme-listener.sh" ]]; then
    echo "Missing II shared palette listener" >&2; failed=1
fi
if [[ ! -f /usr/share/wayland-sessions/niri.desktop ]]; then
    echo 'Missing standard Niri login entry' >&2; failed=1
fi
if [[ "$(basename "$(readlink -f /etc/systemd/system/display-manager.service)")" != gdm.service ]]; then
    echo 'This overlay expects GDM' >&2; failed=1
fi
for unit in niri.service skwd-walld.service ii-skwd-wall-theme.service; do
    if ! systemctl --user cat "$unit" >/dev/null 2>&1; then
        printf 'Cannot read user unit: %s (run from your logged-in desktop)\n' "$unit" >&2
        failed=1
    fi
done
if (( failed )); then exit 1; fi
printf 'Personal overlay preflight passed. No files were installed.\n'
