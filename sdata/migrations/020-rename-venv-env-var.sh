# Migration: Rename ILLOGICAL_IMPULSE_VIRTUAL_ENV → INIR_VENV
# Adds the canonical INIR_VENV alongside the legacy name in shell profiles
# and Niri environment blocks. Scripts already have fallback logic.

MIGRATION_ID="020-rename-venv-env-var"
MIGRATION_TITLE="Rename Python venv environment variable"
MIGRATION_DESCRIPTION="Introduces INIR_VENV as the canonical venv variable. Legacy ILLOGICAL_IMPULSE_VIRTUAL_ENV kept as alias for backwards compatibility."
MIGRATION_TARGET_FILE="Shell profiles + Niri config"
MIGRATION_REQUIRED=true

# Personal overlay: never import II's Python environment or edit shared profiles.
migration_check() { return 1; }
migration_apply() { return 0; }
