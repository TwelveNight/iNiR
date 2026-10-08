#!/usr/bin/env bash
# Compatibility entry point. The policy-only implementation now lives in the
# colour module, including the explicit '#RRGGBB' argument. Both entry points
# preserve browser profiles and existing non-colour policy keys.
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/modules/40-chrome.sh" "$@"
