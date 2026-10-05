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
inir_personal_install_entry "$@"
