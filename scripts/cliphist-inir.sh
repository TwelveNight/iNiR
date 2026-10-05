#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/config-path.sh"
cliphist_state="$(inir_state_dir)/cliphist"
cliphist_config="$(inir_config_dir)/cliphist"
mkdir -p "$cliphist_state" "$cliphist_config"
exec cliphist -config-path "$cliphist_config/config" -db-path "$cliphist_state/db" "$@"
