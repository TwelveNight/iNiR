#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Do not pass the lock-screen password to status checks or child environments.
password="${UNLOCK_PASSWORD-}"
unset UNLOCK_PASSWORD
trap 'unset password' EXIT
status=0
"$SCRIPT_DIR/is_unlocked.sh" || status=$?
[[ "$status" != 0 ]] || exit 0
[[ "$status" == 1 ]] || exit "$status"
if [[ -z "$password" ]]; then
    [[ -t 0 ]] || exit 2
    read -r -s -p 'Login keyring password: ' password || exit 2
    printf '\n' >&2
fi
# Unlock the current daemon over its local control socket; no kill/restart/eval.
printf '%s' "$password" | /usr/bin/python3 "$SCRIPT_DIR/login-keyring.py" --unlock
