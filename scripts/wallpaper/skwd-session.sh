#!/usr/bin/env bash
# Run only after Niri publishes its actual Wayland environment.
set -euo pipefail

if [[ -z "${NIRI_SOCKET:-}" || -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "skwd-session: a running Niri session is required" >&2
    exit 1
fi

systemctl --user import-environment WAYLAND_DISPLAY NIRI_SOCKET XDG_CURRENT_DESKTOP
systemctl --user restart skwd-walld.service

if [[ -x "${XDG_CONFIG_HOME:-$HOME/.config}/quickshell/ii/scripts/colors/skwd-wall-theme-listener.sh" ]]; then
    # One palette owner for both shells; iNiR watches the shared generated files.
    systemctl --user start ii-skwd-wall-theme.service
else
    echo "skwd-session: II's shared palette listener is missing" >&2
    exit 1
fi
