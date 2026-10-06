pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common
import "skwdState.js" as State

Singleton {
    id: root

    property var current: ({})
    property bool available: false
    property string lastError: ""
    property var _queuedApply: null
    readonly property string cacheHome: Quickshell.env("XDG_CACHE_HOME") || (Directories.homePath + "/.cache")
    signal applied(string path, string monitor)

    function control(action: string): void {
        Quickshell.execDetached(["skwd-helm", action])
    }

    function wallpaperPath(monitor = ""): string {
        return State.wallpaperPath(root.current, monitor, root.cacheHome)
    }

    function refresh(): void {
        if (!currentProc.running) currentProc.running = true
        else refreshTimer.restart()
    }

    function apply(path: string, monitor = ""): void {
        if (!path) return
        if (applyProc.running) {
            root._queuedApply = { path: path, monitor: monitor }
            return
        }
        applyProc.path = path
        applyProc.monitor = monitor
        applyProc.command = State.applyCommand(path, monitor)
        applyProc.running = true
    }

    // Query once at startup and after events; no permanent polling in a healthy session.
    Process {
        id: currentProc
        command: ["skwd-helm", "current", "--json"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const reply = JSON.parse(text)
                    if (!reply || !reply.outputs) throw new Error("Missing outputs")
                    if (reply && reply.outputs) {
                        root.current = reply
                        root.available = true
                        root.lastError = ""
                    }
                } catch (error) {
                    root.available = false
                    root.lastError = "Cannot read skwd-wall state: " + error
                }
            }
        }
        onExited: (code) => {
            if (code !== 0) {
                root.available = false
                root.lastError = "skwd-walld is unavailable (" + code + ")"
            }
        }
    }

    Process {
        id: applyProc
        property string path: ""
        property string monitor: ""
        onExited: (code) => {
            if (code === 0) {
                root.applied(path, monitor)
                root.refresh()
            } else {
                root.lastError = "skwd-wall could not apply wallpaper (" + code + ")"
                console.warn(root.lastError)
            }
            const next = root._queuedApply
            root._queuedApply = null
            if (next) Qt.callLater(root.apply, next.path, next.monitor)
        }
    }

    Process {
        id: watchProc
        // Service shutdown/crashes can bypass QML destructors. Tie this listener
        // to its Quickshell parent so the next event cannot hit an orphan's pipe.
        command: ["setpriv", "--pdeathsig", "TERM", "skwd-helm", "watch"]
        stdout: SplitParser {
            onRead: line => {
                try {
                    const event = JSON.parse(line)
                    if (String(event.event || "").startsWith("skwd.wall.")) refreshTimer.restart()
                } catch (error) { /* A malformed event never resets the last good state. */ }
            }
        }
        onExited: reconnectTimer.restart()
    }
    Timer { id: refreshTimer; interval: 180; onTriggered: root.refresh() }
    Timer {
        id: reconnectTimer
        interval: 3000
        onTriggered: { root.refresh(); watchProc.running = true }
    }
    Component.onCompleted: { root.refresh(); watchProc.running = true }
}
