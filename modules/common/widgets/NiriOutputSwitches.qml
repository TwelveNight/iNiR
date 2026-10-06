pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.services
import qs.modules.common

// List IPC outputs, not Quickshell.screens: disabled connectors must stay reachable.
ColumnLayout {
    id: root
    Layout.fillWidth: true
    visible: CompositorService.isNiri
    property bool controlsLocked: false
    property string error: ""
    readonly property var outputs: NiriService.outputs ?? ({})
    readonly property var names: Object.keys(outputs).sort()
    readonly property int activeCount: names.filter(name => isActive(name)).length

    function isActive(name: string): bool {
        const output = outputs[name]
        return output?.current_mode !== null && output?.current_mode !== undefined
            && output?.logical !== null && output?.logical !== undefined
    }

    function changePower(name: string, on: bool): void {
        if (power.running || controlsLocked || (!on && activeCount <= 1))
            return
        error = ""
        power.command = ["python3", Quickshell.shellPath("scripts/niri-config.py"),
            "output-power", name, on ? "on" : "off"]
        power.running = true
    }

    StyledText {
        Layout.fillWidth: true
        text: Translation.tr("Turn individual displays on or off for this session. Saved resolution, scale and position are unchanged. Logging in again or editing the output configuration can reset this choice.")
        wrapMode: Text.WordWrap
        font.pixelSize: Appearance.font.pixelSize.small
        color: Appearance.colors.colSubtext
    }

    Repeater {
        model: root.names
        SettingsSwitch {
            required property string modelData
            Layout.fillWidth: true
            buttonIcon: "monitor"
            text: modelData
            autoToggle: false
            checked: root.isActive(modelData)
            enabled: !root.controlsLocked && !power.running && (!checked || root.activeCount > 1)
            description: checked
                ? (root.activeCount === 1 ? Translation.tr("Last active display") : Translation.tr("Display enabled"))
                : Translation.tr("Display disabled — turn on to use it again")
            onToggledByUser: checked => root.changePower(modelData, checked)
        }
    }

    StyledText {
        Layout.fillWidth: true
        visible: root.error.length > 0
        text: root.error
        color: Appearance.colors.colError
        wrapMode: Text.WordWrap
    }

    Process {
        id: power
        stdout: StdioCollector { id: result }
        stderr: StdioCollector { id: errors }
        onExited: exitCode => {
            if (exitCode !== 0) {
                try { root.error = JSON.parse(result.text).error || Translation.tr("Could not change display state.") }
                catch (e) { root.error = errors.text.trim() || Translation.tr("Could not change display state.") }
            }
            NiriService.fetchOutputs()
        }
    }
    onVisibleChanged: if (visible) NiriService.fetchOutputs()
    Component.onCompleted: if (visible) NiriService.fetchOutputs()
}
