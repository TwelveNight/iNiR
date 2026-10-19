#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
    ""|--enable-timer) ;;
    *) echo 'Usage: install-desktop-update.sh [--enable-timer]' >&2; exit 2 ;;
esac
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
install -Dm755 "$repo/scripts/personal/desktop-update.py" "$HOME/.local/lib/desktop-profiles/desktop_update.py"
mkdir -p "$HOME/.local/bin"
printf '%s\n' '#!/bin/sh' 'exec python3 "$HOME/.local/lib/desktop-profiles/desktop_update.py" "$@"' > "$HOME/.local/bin/desktop-update"
chmod 755 "$HOME/.local/bin/desktop-update"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/desktop-update-check.service" <<'UNIT'
[Unit]
Description=Check official desktop upstreams without merging or deploying

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -B %h/.local/lib/desktop-profiles/desktop_update.py check all --notify
TimeoutStartSec=5min
UNIT
cat > "$HOME/.config/systemd/user/desktop-update-check.timer" <<'UNIT'
[Unit]
Description=Check personal desktop upstreams every six hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
UNIT
if [[ "${1:-}" == --enable-timer ]]; then
    systemctl --user daemon-reload
    systemctl --user enable --now desktop-update-check.timer
fi
