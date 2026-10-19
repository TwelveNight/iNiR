-- Shared desktop services must receive the compositor environment before use.
-- The helper watches this compositor's PID, including an exit without Lua hooks.
hl.on("hyprland.start", function()
    hl.exec_cmd('python3 "$HOME/.local/lib/desktop-profiles/session_runtime.py" start hyprland')
end)
