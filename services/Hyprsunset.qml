pragma Singleton

import QtQuick
import qs.modules.common
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.services

/**
 * Night light service with automatic mode.
 * Uses hyprsunset on Hyprland, wlsunset on Niri.
 */
Singleton {
    id: root
    property string from: Config.options?.light?.night?.from ?? "19:00" 
    property string to: Config.options?.light?.night?.to ?? "06:30"
    property bool automatic: Config.options?.light?.night?.automatic && (Config?.ready ?? true)
    property bool manualEnabled: Config.options?.light?.night?.enabled ?? false
    property int colorTemperature: Config.options?.light?.night?.colorTemperature ?? 5000
    property bool shouldBeOn
    property bool firstEvaluation: true
    property bool active: false

    // A socket plus a bounded user-manager probe, not merely installed tools.
    // A timeout means a busy systemd manager, never permission to spawn an
    // unowned fallback in inir.service's cgroup. Without an owned non-systemd
    // backend, fail closed instead of adopting or killing another wlsunset.
    readonly property string _systemdUserManagerCheck: `
        if [ -S "\${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/systemd/private" ] &&
           [ -x /usr/bin/systemctl ] && [ -x /usr/bin/timeout ]; then
            /usr/bin/timeout 3s /usr/bin/systemctl --user show-environment >/dev/null 2>&1
            case $? in 0|124) ;; *) exit 1 ;; esac
        else
            exit 1
        fi;
    `

    property int fromHour: Number(from.split(":")[0])
    property int fromMinute: Number(from.split(":")[1])
    property int toHour: Number(to.split(":")[0])
    property int toMinute: Number(to.split(":")[1])

    property int clockHour: DateTime.clock.hours
    property int clockMinute: DateTime.clock.minutes

    property var manualActive
    property int manualActiveHour
    property int manualActiveMinute

    // Debounce timer for wlsunset restarts
    property bool _pendingRestart: false
    Timer {
        id: restartDebounce
        interval: 300
        onTriggered: {
            if (root._pendingRestart && root.active) {
                root.enable()
            }
            root._pendingRestart = false
        }
    }

    onClockMinuteChanged: reEvaluate()
    onAutomaticChanged: {
        root.manualActive = undefined;
        root.firstEvaluation = true;
        reEvaluate();
    }

    function inBetween(t, from, to) {
        if (from < to) {
            return (t >= from && t <= to);
        } else {
            // Wrapped around midnight
            return (t >= from || t <= to);
        }
    }

    function reEvaluate() {
        const t = clockHour * 60 + clockMinute;
        const from = fromHour * 60 + fromMinute;
        const to = toHour * 60 + toMinute;
        const manualActive = manualActiveHour * 60 + manualActiveMinute;

        if (root.manualActive !== undefined && (inBetween(from, manualActive, t) || inBetween(to, manualActive, t))) {
            root.manualActive = undefined;
        }
        root.shouldBeOn = inBetween(t, from, to);
        if (firstEvaluation) {
            firstEvaluation = false;
            root.ensureState();
        }
    }

    onShouldBeOnChanged: ensureState()
    function ensureState() {
        if (root.manualActive !== undefined)
            return;

        if (root.automatic) {
            if (root.shouldBeOn) {
                root.enable();
            } else {
                root.disable();
            }
        } else if (root.manualEnabled) {
            root.enable();
        } else {
            root.disable();
        }
    }

    function load() { } // Dummy to force init

    function _doEnable() {
        if (CompositorService.isNiri) {
            wlsunsetStartProc.running = true;
        } else {
            hyprsunsetStartProc.running = true;
        }
    }

    function enable() {
        root.active = true;
        if (CompositorService.isNiri) {
            // Kill first, then start after kill completes
            wlsunsetKillProc.running = true;
        } else {
            root._doEnable();
        }
    }

    function disable() {
        root.active = false;
        if (CompositorService.isNiri) {
            wlsunsetKillProc.running = true;
        } else {
            hyprsunsetKillProc.running = true;
        }
    }

    function fetchState() {
        if (CompositorService.isNiri) {
            niriFetchProc.running = true;
        } else {
            fetchProc.running = true;
        }
    }

    // === Hyprland processes ===
    Process {
        id: hyprsunsetStartProc
        command: ["/usr/bin/bash", "-c", `pidof hyprsunset || /usr/bin/hyprsunset --temperature ${root.colorTemperature}`]
    }

    Process {
        id: hyprsunsetKillProc
        command: ["/usr/bin/pkill", "-x", "hyprsunset"]
    }

    Process {
        id: fetchProc
        running: !CompositorService.isNiri
        command: ["/usr/bin/bash", "-c", "hyprctl hyprsunset temperature"]
        stdout: StdioCollector {
            id: stateCollector
            onStreamFinished: {
                const output = stateCollector.text.trim();
                if (output.length == 0 || output.startsWith("Couldn't"))
                    root.active = false;
                else
                    root.active = (output != "6500"); // 6500 is the default when off
            }
        }
    }

    // === Niri processes (wlsunset) ===
    Process {
        id: wlsunsetStartProc
        // Only the transient unit owns the daemon, outside the shell cgroup;
        // it survives shell reloads but stops with the Niri session.
        command: ["/usr/bin/bash", "-c", root._systemdUserManagerCheck + `
            [ -x /usr/bin/systemd-run ] || exit 1
            exec /usr/bin/systemd-run --user --collect --unit=inir-wlsunset.service --property=PartOf=niri.service /usr/bin/wlsunset -T 6500 -t "$1" -s 00:00 -S 23:59
        `, "inir-nightlight", root.colorTemperature.toString()]
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0) root.active = false;
        }
    }

    Process {
        id: wlsunsetKillProc
        // Stop only our own unit; another session may own its own wlsunset.
        command: ["/usr/bin/bash", "-c", root._systemdUserManagerCheck +
            "/usr/bin/systemctl --user stop inir-wlsunset.service >/dev/null 2>&1 || true"]
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0) {
                root.active = false;
                return;
            }
            // If we're enabling, start wlsunset after kill completes
            if (root.active) {
                root._doEnable();
            }
        }
    }

    Process {
        id: niriFetchProc
        running: CompositorService.isNiri
        command: ["/usr/bin/bash", "-c", root._systemdUserManagerCheck +
            "exec /usr/bin/systemctl --user is-active --quiet inir-wlsunset.service"]
        onExited: (exitCode, exitStatus) => {
            root.active = (exitCode === 0);
        }
    }

    function toggle(active = undefined) {
        if (root.manualActive === undefined) {
            root.manualActive = root.active;
            root.manualActiveHour = root.clockHour;
            root.manualActiveMinute = root.clockMinute;
        }

        root.manualActive = active !== undefined ? active : !root.manualActive;
        Config.setNestedValue("light.night.enabled", root.manualActive);
        if (root.manualActive) {
            root.enable();
        } else {
            root.disable();
        }
    }

    // React to temperature changes while active
    Connections {
        target: Config.options?.light?.night ?? null
        enabled: !!(Config.options?.light?.night)
        
        function onColorTemperatureChanged() {
            if (!root.active) return;
            const temp = Config.options?.light?.night?.colorTemperature ?? root.colorTemperature;
            
            if (CompositorService.isNiri) {
                // Queue restart with debounce
                root._pendingRestart = true;
                restartDebounce.restart();
            } else {
                Quickshell.execDetached(["/usr/bin/hyprctl", "hyprsunset", "temperature", `${temp}`]);
            }
        }
    }

    // React to schedule changes while automatic mode is on
    Connections {
        target: Config.options?.light?.night ?? null
        enabled: root.automatic && !!(Config.options?.light?.night)
        
        function onFromChanged() {
            root.firstEvaluation = true;
            root.reEvaluate();
        }
        
        function onToChanged() {
            root.firstEvaluation = true;
            root.reEvaluate();
        }
    }
}
