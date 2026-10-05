#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/config-path.sh"
mkdir -p "$(inir_temp_dir)/keyring" || exit 3
error_file=$(mktemp "$(inir_temp_dir)/keyring/lookup.XXXXXX") || exit 3
trap 'rm -f "$error_file"' EXIT

lookup_status=0
data=$(secret-tool lookup application illogical-impulse 2>"$error_file") || lookup_status=$?
if [[ "$lookup_status" == 0 && -n "$data" ]]; then
    printf '%s\n' "$data"
    exit 0
fi
# Locked/unavailable is never equivalent to an empty store. Do not disclose
# backend errors (or credentials) to the UI log.
"$SCRIPT_DIR/is_unlocked.sh" >/dev/null 2>&1 || exit 2
[[ "$lookup_status" == 1 && ! -s "$error_file" && -z "$data" ]] && exit 1
exit 3
