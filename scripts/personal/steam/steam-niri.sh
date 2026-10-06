#!/usr/bin/env bash
set -euo pipefail
# Preserve Hyprland and deliberate debugger sessions. No global GPU/library env.
launcher="${XDG_CONFIG_HOME:-$HOME/.config}/quickshell/inir/scripts/personal/steam/launch-client.sh"
lib="${XDG_DATA_HOME:-$HOME/.local/share}/inir/steam/gtk2-randr-guard.so"
if [[ -S "${NIRI_SOCKET:-}" && -z "${DEBUGGER:-}" && -x "$launcher" && -f "$lib" ]]; then
    export DEBUGGER="$launcher"
fi
exec /usr/bin/steam "$@"
