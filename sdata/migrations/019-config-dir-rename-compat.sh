#!/usr/bin/env bash
MIGRATION_ID="019-config-dir-rename-compat"
MIGRATION_TITLE="Keep II configuration separate"
MIGRATION_DESCRIPTION="The personal overlay uses ~/.config/inir without moving or linking II settings."
MIGRATION_TARGET_FILE="~/.config/inir"
MIGRATION_REQUIRED=false
migration_check() { return 1; }
migration_preview() { echo "II settings are kept in their original directory."; }
migration_apply() { :; }
