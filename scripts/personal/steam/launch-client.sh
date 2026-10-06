#!/usr/bin/env bash
set -euo pipefail
# Steam invokes this through its documented DEBUGGER launcher hook, after its
# runtime and updates are ready. The library removes itself from the child env.
lib="${XDG_DATA_HOME:-$HOME/.local/share}/inir/steam/gtk2-randr-guard.so"
if [[ ! -f "$lib" || "${1##*/}" != steam ]]; then
    exec "$@"
fi
export INIR_STEAM_PREVIOUS_PRELOAD="${LD_PRELOAD:-}"
export LD_PRELOAD="$lib${LD_PRELOAD:+:$LD_PRELOAD}"
exec "$@"
