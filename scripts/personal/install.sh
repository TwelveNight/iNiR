#!/usr/bin/env bash
# Save affected live paths, then deploy the personal branch.
set -euo pipefail

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    printf '%s\n' 'Usage: ./scripts/personal/install.sh [--check | -y]' \
        '  --check: read-only preflight; -y: deploy without per-step prompts' \
        'Backs up and deploys iNiR; preserves GDM and existing application settings.' \
        'Uses existing system dependencies and a private iNiR Python environment.'
    exit 0
fi

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
state_home="${XDG_STATE_HOME:-$HOME/.local/state}"
config_dir="${INIR_CONFIG_DIR:-$config_home/inir}"
state_dir="${INIR_STATE_DIR:-$state_home/inir}"
export INIR_CONFIG_DIR="$config_dir" INIR_STATE_DIR="$state_dir"
export DOTS_CORE_CONFDIR="$config_dir"
export INIR_VENV="${INIR_VENV:-$state_dir/.venv}"
export INIR_WALLPAPER_BACKEND=skwd-wall
export INIR_INSTALL_SHARED_APP_CONFIGS=false INIR_INSTALL_SHELL_PROFILES=false

check_only=false
for option in "$@"; do
    [[ "$option" != --check ]] || check_only=true
    [[ "$option" == --check || "$option" == -y || "$option" == --yes || "$option" == --quiet || "$option" == -q ]] || { echo "Unsupported install option: $option" >&2; exit 2; }
done

# Login owns the canonical compositor link. Never update a different profile.
profile_manager="${HOME}/.local/bin/desktop-profile"
if [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/desktop-profiles/profiles.json" ]]; then
    [[ -x "$profile_manager" ]] || { echo 'Missing desktop-profile manager' >&2; exit 1; }
    case "${1:-}" in
        -h|--help|help|status|version|info|doctor|checkdeps) ;;
        *) "$profile_manager" guard inir || exit $? ;;
    esac
fi

python3 "$repo/scripts/lib/private_paths.py" --runtime-links
"$repo/scripts/personal/preflight.sh"
[[ "$check_only" != true ]] || exit 0
bash "$repo/scripts/personal/install-desktop-update.sh"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "$XDG_RUNTIME_DIR/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

snapshot="$state_dir/install-backups/$(date +%Y%m%d-%H%M%S)-$$"
umask 077
mkdir -p "$snapshot/config" "$snapshot/state"
# Keep the previous user autostart choices available for rollback.
for name in org.kde.kgpg.desktop org.kde.kalendarac.desktop org.kde.kclockd-autostart.desktop todesk.desktop; do
    if [[ -e "$config_home/autostart/$name" || -L "$config_home/autostart/$name" ]]; then
        mkdir -p "$snapshot/config/autostart"
        cp -a "$config_home/autostart/$name" "$snapshot/config/autostart/$name"
    fi
done
# Back up shared lifecycle overrides separately from the user's desktop units.
for name in systemd/user/inir-hyprland-watch.service systemd/user/desktop-profile-hyprland-watch.service systemd/user/hyprland-session.target.d systemd/user/app-.service.d; do
    if [[ -e "$config_home/$name" || -L "$config_home/$name" ]]; then
        mkdir -p "$snapshot/config/$(dirname "$name")"
        cp -a "$config_home/$name" "$snapshot/config/$name"
    fi
done
for name in systemd/user/inir-output-wallpaper.service systemd/user/niri.service.wants/inir-output-wallpaper.service niri xdg-desktop-portal/niri-portals.conf systemd/user/inir.service systemd/user/inir.service.d systemd/user/niri.service.d systemd/user/niri.service.wants/inir.service systemd/user/app-org.kde.xwaylandvideobridge@autostart.service.d systemd/user/hyprland-session.target hypr/hyprland/execs.lua hypr/custom/execs.lua hypr/custom/inir-session.lua systemd/user/skwd-walld.service.d systemd/user/ii-skwd-wall-theme.service.d systemd/user/graphical-session.target.wants/docker-desktop.service systemd/user/graphical-session.target.wants/app-dev.lizardbyte.app.Sunshine.service systemd/user/sunshine.service; do
    if [[ -e "$config_home/$name" || -L "$config_home/$name" ]]; then
        mkdir -p "$snapshot/config/$(dirname "$name")"
        if [[ "$name" == niri && -L "$config_home/niri" && -f "$config_home/desktop-profiles/profiles.json" ]]; then
            # Save installed contents, not a relative link that is dangling in
            # the snapshot. Keep the login selector separately for rollback.
            "$profile_manager" guard inir
            readlink -- "$config_home/niri" > "$snapshot/niri-link"
            cp -a "$(realpath -e -- "$config_home/niri")" "$snapshot/config/niri"
        else
            cp -a "$config_home/$name" "$snapshot/config/$name"
        fi
    fi
done
# Service wiring removes obsolete iNiR links from other targets. Preserve those
# exact directory entries too, including dangling links; never copy entire units.
for link in "$config_home"/systemd/user/*.wants/inir.service; do
    [[ -e "$link" || -L "$link" ]] || continue
    name="${link#"$config_home/"}"
    [[ -e "$snapshot/config/$name" || -L "$snapshot/config/$name" ]] && continue
    mkdir -p "$snapshot/config/$(dirname "$name")"
    cp -a "$link" "$snapshot/config/$name"
done
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
for name in applications/inir.desktop applications/inir-settings.desktop icons/hicolor/scalable/apps/inir.svg dbus-1/services/org.freedesktop.secrets.service dbus-1/services/org.gnome.keyring.service; do
    if [[ -e "$data_home/$name" || -L "$data_home/$name" ]]; then
        mkdir -p "$snapshot/data/$(dirname "$name")"
        cp -a "$data_home/$name" "$snapshot/data/$name"
    fi
done
if [[ -d "$config_home/quickshell/inir" ]]; then
    cp -a "$config_home/quickshell/inir" "$snapshot/runtime"
fi
if [[ -d "$state_dir/user" ]]; then
    cp -a "$state_dir/user" "$snapshot/state/user"
fi
if [[ -d "$config_dir" ]]; then
    cp -a "$config_dir" "$snapshot/inir-config"
fi
readlink -f /etc/systemd/system/display-manager.service > "$snapshot/display-manager"
printf 'Backup: %s\n' "$snapshot"

# Groups and system desktop preferences are already configured on this host.
# Only iNiR's own marker decides first-run behavior; never change II's marker.
launcher="${XDG_BIN_HOME:-$HOME/.local/bin}/inir"
if [[ -e "$launcher" || -L "$launcher" ]]; then
    cp -a "$launcher" "$snapshot/launcher"
fi
cd "$repo"
INIR_PERSONAL_INSTALL_STAGE=files ./setup install --skip-deps --skip-setups "$@"
python3 "$repo/scripts/personal/configure-session.py"
"$repo/scripts/personal/disable-autostart.sh"
python3 "$repo/scripts/personal/configure-autostart.py"
python3 "$repo/scripts/personal/configure-keyring.py"
systemctl --user daemon-reload
niri validate --config "$config_home/niri/config.kdl"
[[ -x "$launcher" && -f "$config_dir/installed_true" ]] || { echo 'Incomplete launcher/config install' >&2; exit 1; }
[[ -L "$config_home/systemd/user/niri.service.wants/inir.service" ]] || { echo 'Missing Niri service wiring' >&2; exit 1; }
"$INIR_VENV/bin/python3" - <<'PYCHECK'
import cv2, PIL, numpy, ytmusicapi
from materialyoucolor.palettes.tonal_palette import TonalPalette
assert isinstance(TonalPalette.from_hue_and_chroma(220, 20).tone(50), int), "materialyoucolor v3 is required"
PYCHECK
printf 'Choose Niri in GDM on your next login.\n'
