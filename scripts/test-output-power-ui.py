#!/usr/bin/env python3
"""Load the real output switch component with fake compositor state, offscreen."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='inir-output-ui-') as temp:
    base = Path(temp)
    def write(path, text):
        target = base / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    write('services/qmldir', 'singleton NiriService 1.0 NiriService.qml\nsingleton CompositorService 1.0 CompositorService.qml\n')
    write('services/CompositorService.qml', 'pragma Singleton\nimport QtQuick\nQtObject { property bool isNiri: true }')
    write('services/NiriService.qml', '''pragma Singleton
import QtQuick
QtObject {
 property var outputs: ({"HDMI-A-1": {current_mode: 0, logical: {}}, "eDP-2": {current_mode: null, logical: null}})
 function fetchOutputs() {}
}''')
    write('modules/common/qmldir', 'singleton Appearance 1.0 Appearance.qml\nsingleton Translation 1.0 Translation.qml\n')
    write('modules/common/Appearance.qml', '''pragma Singleton
import QtQuick
QtObject {
 property var font: ({pixelSize: {small: 12}})
 property var colors: ({colSubtext: "gray", colError: "red"})
}''')
    write('modules/common/Translation.qml', 'pragma Singleton\nimport QtQuick\nQtObject { function tr(s) { return s } }')
    write('modules/common/widgets/qmldir', 'NiriOutputSwitches 1.0 NiriOutputSwitches.qml\nSettingsSwitch 1.0 SettingsSwitch.qml\nStyledText 1.0 StyledText.qml\n')
    write('modules/common/widgets/StyledText.qml', 'import QtQuick\nText {}')
    write('modules/common/widgets/SettingsSwitch.qml', '''import QtQuick
Rectangle {
 property string buttonIcon
 property string text
 property string description
 property bool autoToggle
 property bool checked
 signal toggledByUser(bool checked)
}''')
    shutil.copyfile(ROOT / 'modules/common/widgets/NiriOutputSwitches.qml', base / 'modules/common/widgets/NiriOutputSwitches.qml')
    write('shell.qml', '''import QtQuick
import Quickshell
import qs.services
import qs.modules.common.widgets
Scope {
 NiriOutputSwitches { id: switches }
 property int step: 0
 function check(ok, message) { if (!ok) throw new Error(message) }
 Timer {
  interval: 40; running: true; repeat: true
  onTriggered: {
   try {
    const repeater = switches.children.find(child => typeof child.itemAt === "function")
    if (step === 0) {
     check(repeater.count === 2, "Disabled connector missing")
     check(repeater.itemAt(0).checked && !repeater.itemAt(0).enabled, "Last output is not protected")
     check(!repeater.itemAt(1).checked && repeater.itemAt(1).enabled, "Disabled connector cannot be enabled")
     NiriService.outputs = {"HDMI-A-1": {current_mode: 0, logical: {}}, "eDP-2": {current_mode: 1, logical: {}}}
    } else if (step === 1) {
     check(repeater.itemAt(0).enabled && repeater.itemAt(1).enabled, "Live state did not refresh")
     switches.controlsLocked = true
    } else if (step === 2) {
     check(!repeater.itemAt(0).enabled && !repeater.itemAt(1).enabled, "Preview transaction not respected")
     switches.controlsLocked = false
     NiriService.outputs = {"HDMI-A-1": {current_mode: 0, logical: {}}}
    } else {
     check(repeater.count === 1 && !repeater.itemAt(0).enabled, "Hot unplug protection failed")
     console.log("OUTPUT_POWER_UI_PASS")
     Qt.quit()
    }
    step++
   } catch (e) { console.error("OUTPUT_POWER_UI_FAIL", e); Qt.quit() }
  }
 }
}''')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QSG_RHI_BACKEND='software')
    result = subprocess.run(['qs', '-p', str(base), '--no-color'], env=env, capture_output=True, text=True, timeout=15)
    log = result.stdout + result.stderr
    if 'OUTPUT_POWER_UI_PASS' not in log or 'OUTPUT_POWER_UI_FAIL' in log:
        raise SystemExit(log)
    print('PASS actual QML: disabled connectors, last-active guard, live refresh, preview lock and hot unplug')
