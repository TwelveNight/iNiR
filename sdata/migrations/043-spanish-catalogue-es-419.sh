#!/usr/bin/env bash
# Migration 043: the Spanish catalogue is neutral Latin American Spanish now, es_419 instead of es_AR.

MIGRATION_ID="043-spanish-catalogue-es-419"
MIGRATION_TITLE="Point Spanish at the new catalogue"
MIGRATION_DESCRIPTION="Spanish moved from es_AR to es_419 (neutral Latin American Spanish). A language picked as es_AR follows it, so the language picker shows it selected."
MIGRATION_TARGET_FILE="~/.config/inir/config.json"
MIGRATION_REQUIRED=false

_config_path() {
  printf '%s\n' "${INIR_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/inir}/config.json"
}

migration_check() {
  local conf
  conf="$(_config_path)"
  [[ -f "$conf" ]] || return 1
  jq -e '.language.ui == "es_AR"' "$conf" >/dev/null 2>&1
}

migration_preview() {
  echo "  language.ui: es_AR -> es_419"
}

migration_apply() {
  local conf tmp
  conf="$(_config_path)"
  [[ -f "$conf" ]] || return 0
  command -v jq >/dev/null 2>&1 || return 1

  tmp="${conf}.migration-tmp.$$"
  jq '.language.ui = "es_419"' "$conf" > "$tmp" && mv "$tmp" "$conf"
}
