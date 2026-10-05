# Conflict detection for iNiR
# Checks for packages that might conflict with Quickshell's functionality

check_conflicts() {
    # The personal overlay runs only in the Niri session. Other installed shells
    # and wallpaper tools remain available for their own sessions.
    log_info "Personal overlay: preserving existing desktop packages and services"
}
