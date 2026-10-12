#!/usr/bin/env bash
# Templates are rendered before applycolor dispatches its modules.
set -euo pipefail
busctl --user --auto-start=no call org.fcitx.Fcitx5 /controller \
    org.fcitx.Fcitx.Controller1 ReloadAddonConfig s classicui >/dev/null 2>&1 || true
