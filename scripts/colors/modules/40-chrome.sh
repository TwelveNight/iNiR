#!/usr/bin/env bash
# Chromium browsers take one colour, the BrowserThemeColor policy, and build their whole palette from it. Its tone
# decides light or dark, so they get the header bar colour, never the accent. A running browser watches its policy
# folder and repaints after the file changes, so nothing is launched. The personal overlay only uses existing
# writable policy folders: never elevate, change permissions, edit profiles or replace unrelated policies.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/module-runtime.sh"
COLOR_MODULE_ID="chrome"

POLICY_FILE="ii-theme.json"


# The header bar colour: the browser's frame is built from it (a tinted accent would turn a dark shell's browser light).
header_colour() {
  local palette
  for palette in app-palette.json palette.json; do
    palette="$STATE_DIR/user/generated/$palette"
    [[ -s "$palette" ]] || continue
    jq -r '.app_headerbar_bg // .app_surface // .surface_container_low // .surface // .background // empty' "$palette" \
      2>/dev/null | grep -xiE '#[0-9a-f]{6}' && return 0
  done
  return 1
}

write_policy() {
  local dir="$1" colour="$2" status=0
  [[ "$colour" =~ ^#[0-9A-Fa-f]{6}$ ]] || return 1
  if [[ ! -d "$dir" || ! -w "$dir" ]]; then
    log_module "$dir not writable - colour skipped"
    return 0
  fi
  # Do not follow policy links to unrelated files or browser profiles.
  if [[ -L "$dir/$POLICY_FILE" ]]; then
    log_module "$dir/$POLICY_FILE is a link - left alone"
    return 0
  fi
  printf '{"BrowserThemeColor":"%s"}\n' "$colour" \
    | python3 "$SCRIPT_DIR/lib/shared-theme-config.py" chrome "$dir/$POLICY_FILE" || status=$?
  if [[ "$status" -eq 0 ]]; then
    log_module "wrote $dir/$POLICY_FILE ($colour)"
  elif [[ "$status" -gt 1 ]]; then
    log_module "$dir/$POLICY_FILE invalid or unwritable - left alone"
  else
    return 0
  fi
}

main() {
  command -v jq >/dev/null 2>&1 || { log_module "jq not installed - skipping"; exit 0; }
  # A disabled writer leaves shared policies alone, including non-colour keys.
  [[ "$(config_bool '.appearance.wallpaperTheming.enableChrome' true)" == "true" ]] || return 0
  local browsers=() entry dir colour seen=" "
  mapfile -t browsers < <(installed_chromium_browsers)
  (( ${#browsers[@]} )) || return 0
  colour="${1:-}"
  if [[ -n "$colour" ]]; then
    [[ "$colour" =~ ^#[0-9A-Fa-f]{6}$ ]] || { log_module "invalid explicit colour - skipping"; return 2; }
  else
    colour="$(header_colour)" || { log_module "no app palette yet - skipping"; return 0; }
  fi
  for entry in "${browsers[@]}"; do
    dir="${entry%%|*}"
    if [[ "$seen" != *" $dir "* ]]; then
      write_policy "$dir" "$colour"
      seen+="$dir "
    fi
  done
}

main "$@"
