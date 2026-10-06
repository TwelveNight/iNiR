-- Shared desktop services must receive the compositor environment before use.
-- The helper watches this compositor's PID, including an exit without Lua hooks.
hl.on("hyprland.start", function()
    hl.exec_cmd('python3 "${XDG_CONFIG_HOME:-$HOME/.config}/quickshell/inir/scripts/personal/desktop-session.py" start hyprland')
end)
