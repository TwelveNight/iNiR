#!/usr/bin/env bash
# Scan custom widgets directory and output JSON manifest list
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/widgets/manage.py" scan "${1:?Usage: scan-widgets.sh <widgets-dir>}"
