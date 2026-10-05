#!/usr/bin/env bash

# Library file: intended to be sourced by other scripts.
# Do not set shell options here; callers own execution mode.

# Personal overlay: II owns illogical-impulse; iNiR must never adopt it.

XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

INIR_CONFIG_DIR_NEW="${XDG_CONFIG_HOME}/inir"

inir_config_dir() {
    printf '%s\n' "${INIR_CONFIG_DIR:-$INIR_CONFIG_DIR_NEW}"
}

inir_state_dir() {
    printf '%s\n' "${INIR_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/inir}"
}

inir_temp_dir() {
    if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
        printf '%s/inir\n' "$XDG_RUNTIME_DIR"
    else
        printf '%s/inir/tmp\n' "${XDG_CACHE_HOME:-$HOME/.cache}"
    fi
}

inir_config_file() {
    printf '%s/config.json\n' "$(inir_config_dir)"
}

inir_version_file() {
    printf '%s/version.json\n' "$(inir_config_dir)"
}

inir_installed_marker_file() {
    printf '%s/installed_true\n' "$(inir_config_dir)"
}

inir_migrations_state_file() {
    printf '%s/migrations.json\n' "$(inir_config_dir)"
}
