#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
install -Dm755 "$repo/scripts/personal/desktop-update.py" "$HOME/.local/lib/desktop-profiles/desktop_update.py"
mkdir -p "$HOME/.local/bin"
printf '%s\n' '#!/bin/sh' 'exec python3 "$HOME/.local/lib/desktop-profiles/desktop_update.py" "$@"' > "$HOME/.local/bin/desktop-update"
chmod 755 "$HOME/.local/bin/desktop-update"
