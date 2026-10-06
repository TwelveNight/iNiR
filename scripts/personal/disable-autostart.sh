#!/usr/bin/env bash
# Disable only the requested desktop services; retain manual launch and Docker Engine.
set -euo pipefail
for unit in docker-desktop.service app-dev.lizardbyte.app.Sunshine.service; do
    if systemctl --user cat "$unit" >/dev/null 2>&1; then
        systemctl --user disable "$unit"
    fi
done
