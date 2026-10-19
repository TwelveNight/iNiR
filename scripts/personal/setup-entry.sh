#!/usr/bin/env bash
# Sourced before upstream setup initialization, including its cleanup traps.
# Route the usual CLI to the overlay workflow; its child runs only the files stage.
inir_personal_install_entry() {
    [[ "${INIR_PERSONAL_INSTALL_STAGE:-}" != files ]] || return 0
    local command="" arg
    local -a options=()
    for arg in "$@"; do
        case "$arg" in
            -h|--help) return 0 ;;
            install|reinstall)
                [[ -z "$command" ]] || return 0
                command=install
                ;;
            -y|--yes|-q|--quiet|--check) options+=("$arg") ;;
            *)
                [[ "$command" == install ]] || return 0
                options+=("$arg")
                ;;
        esac
    done
    [[ "$command" == install ]] || return 0
    exec "$REPO_ROOT/scripts/personal/install.sh" "${options[@]}"
}

# Login owns the canonical compositor link. Never update a different profile.
# Source integration is independent of the currently selected compositor.
if [[ "${DESKTOP_UPDATE_LOCAL:-}" != 1 && -f "${HOME}/.config/desktop-profiles/profiles.json" ]]; then
    update_command=""; local_update=false; source_only=false; unsupported=false
    for argument in "$@"; do
        case "$argument" in
            -y|--yes|-q|--quiet) ;;
            update) update_command=update ;;
            --local) local_update=true ;;
            --no-deploy) source_only=true ;;
            *) unsupported=true ;;
        esac
    done
    if [[ "$update_command" == update && "$local_update" != true ]]; then
        [[ "$unsupported" != true ]] || { echo 'Use desktop-update update inir, or inir update --local.' >&2; exit 2; }
        if [[ "$source_only" == true ]]; then
            exec "$HOME/.local/bin/desktop-update" sync inir
        fi
        exec "$HOME/.local/bin/desktop-update" update inir
    fi
fi
profile_manager="${HOME}/.local/bin/desktop-profile"
if [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/desktop-profiles/profiles.json" ]]; then
    [[ -x "$profile_manager" ]] || { echo 'Missing desktop-profile manager' >&2; exit 1; }
    case "${1:-}" in
        -h|--help|help|status|version|info|doctor|checkdeps) ;;
        *) "$profile_manager" guard inir || exit $? ;;
    esac
fi

inir_personal_install_entry "$@"
