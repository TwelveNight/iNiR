#!/usr/bin/env bash
# Open a Secret Service session before reading Collection.Locked (GNOME 50).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unset UNLOCK_PASSWORD
exec /usr/bin/python3 "$SCRIPT_DIR/login-keyring.py" --status
