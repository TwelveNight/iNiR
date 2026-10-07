pragma ComponentBehavior: Bound

import QtQuick
import qs.services

// One startup pass over existing mixer identities. No delegates, polling or
// input surfaces are created here; lookups fill the shared bounded caches.
QtObject {
    id: root
    property bool active: false
    property bool paused: false
    readonly property bool ready: root.active && Audio.ready
    property bool started: false
    property bool complete: false
    property var pending: []
    property int processed: 0
    property real startedAt: 0
    signal finished(int count, real elapsed)

    onActiveChanged: if (!root.active) {
        root.pending = []
        root.started = false
        root.complete = false
        root.processed = 0
    }
    function finish(): void {
        root.pending = []
        root.complete = true
        root.finished(root.processed, Date.now() - root.startedAt)
    }
    property Timer startDelay: Timer {
        interval: 250
        running: root.ready && !root.paused && !root.started
        onTriggered: {
            root.started = true
            root.startedAt = Date.now()
            root.pending = Array.from(Audio.outputAppNodes ?? []).filter(node => node?.audio)
            if (root.pending.length === 0) root.finish()
        }
    }
    property Timer nextIdentity: Timer {
        interval: 32
        repeat: true
        running: root.ready && root.started && !root.complete && !root.paused
        onTriggered: {
            const node = root.pending.shift()
            // A stream may disappear between the snapshot and its turn.
            if (node?.audio) {
                MprisController.streamIconName(node)
                MprisController.streamDisplayName(node)
                root.processed++
            }
            if (root.pending.length === 0) root.finish()
        }
    }
}
