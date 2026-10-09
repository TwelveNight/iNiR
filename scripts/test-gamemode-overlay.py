#!/usr/bin/env python3
"""Exercise production GameMode QML lifecycle with isolated async executables."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-overlay-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for folder in ["services", "modules/common/functions", "bin", "runtime", "state/inir/user"]:
            (self.base / folder).mkdir(parents=True)
        (self.base / "runtime").chmod(0o700)
        source = (ROOT / "services/GameMode.qml").read_text()
        # Redirect only the host systemd-presence probe; retain all state/event logic.
        source = source.replace("[ -d /run/systemd/system ]", '[ -d \\"$HOME/systemd\\" ]')
        (self.base / "services/GameMode.qml").write_text(source)
        (self.base / "services/qmldir").write_text("singleton GameMode 1.0 GameMode.qml\n")
        self.stub("services", "CompositorService", "property bool isNiri: false")
        self.stub("services", "NiriService", "property var liveWindows: []; property var workspaces: ({}); property var outputs: ({})")
        self.stub("modules/common", "Config", '''property var options: ({gameMode: {
            autoDetect: false, disableNiriAnimations: false, disableDiscoverOverlay: true}})
            function disableOverlay() { options = {gameMode: {autoDetect: false,
                disableNiriAnimations: false, disableDiscoverOverlay: false}} }''')
        self.stub("modules/common", "Directories", '''property string stateUserPath: Quickshell.env("HOME") + "/state/inir/user"''')
        self.stub("modules/common/functions", "ShellExec", '''function execDetachedArgs(args, label) { Quickshell.execDetached(args) }''')
        (self.base / "qmldir").write_text("module qs\n")
        self.stub(".", "GlobalStates", "property bool fixture: true")
        self.executable("pgrep", "exit 0")
        self.executable("pkill", '''printf 'stop-begin\n' >> "$HOME/actions.log"
sleep 2
printf 'stop-end\n' >> "$HOME/actions.log"''')
        self.executable("discover-overlay", '''printf 'start-process\n' >> "$HOME/actions.log"''')
        self.executable("systemctl", '''case "$*" in
*is-active*) exit 0;;
*stop*) printf 'stop-begin\n' >> "$HOME/actions.log"; sleep 2; printf 'stop-end\n' >> "$HOME/actions.log";;
*start*) printf 'start-unit\n' >> "$HOME/actions.log";;
*) exit 9;;
esac''')
        self.env = dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.base / "config"),
                        XDG_STATE_HOME=str(self.base / "state"), XDG_CACHE_HOME=str(self.base / "cache"),
                        XDG_DATA_HOME=str(self.base / "data"), XDG_RUNTIME_DIR=str(self.base / "runtime"),
                        QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QS_DEBUG="0",
                        PATH=str(self.base / "bin") + ":" + os.environ["PATH"])
        for key in ["INIR_CONFIG_DIR", "INIR_STATE_DIR", "INIR_RUNTIME_DIR", "INIR_VENV", "DOTS_CORE_CONFDIR"]:
            self.env.pop(key, None)
        for key in ["WAYLAND_DISPLAY", "DISPLAY", "NIRI_SOCKET"]:
            self.env.pop(key, None)

    def stub(self, folder, name, body):
        target = self.base / folder
        (target / f"{name}.qml").write_text(
            f"pragma Singleton\nimport QtQuick\nimport Quickshell\nQtObject {{ {body} }}\n")
        with (target / "qmldir").open("a") as handle:
            handle.write(f"singleton {name} 1.0 {name}.qml\n")

    def executable(self, name, body):
        path = self.base / "bin" / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_qml(self, events, finish=4500):
        timers = "\n".join(f"Timer {{ running: true; interval: {ms}; onTriggered: {{ {action} }} }}"
                            for ms, action in events)
        (self.base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.common
ShellRoot {
    property var service: GameMode
    EVENTS
    Timer { running: true; interval: FINISH; onTriggered: {
        console.log("PASS overlay harness completed"); Qt.quit()
    } }
}
'''.replace("EVENTS", timers).replace("FINISH", str(finish)))
        result = subprocess.run(["dbus-run-session", "--", "qs", "-p", str(self.base), "--no-color"],
                                env=self.env, capture_output=True, text=True, timeout=finish / 1000 + 6)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("PASS overlay harness completed", output, output)
        for error in ["ReferenceError", "TypeError", "Failed to load configuration", "Error:"]:
            self.assertNotIn(error, output, output)
        log = self.base / "actions.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_inactive_before_stop_finishes_restores_process(self):
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "GameMode._manualActive = false")])
        self.assertEqual(actions, ["stop-begin", "stop-end", "start-process"])

    def test_inactive_before_stop_finishes_restores_unit(self):
        (self.base / "systemd").mkdir()
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "GameMode._manualActive = false")])
        self.assertEqual(actions, ["stop-begin", "stop-end", "start-unit"])

    def test_option_disabled_during_stop_restores(self):
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "Config.disableOverlay()")])
        self.assertEqual(actions, ["stop-begin", "stop-end", "start-process"])

    def test_reactivation_during_stop_does_not_start_or_stop_twice(self):
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "GameMode._manualActive = false"),
                                (2200, "GameMode._manualActive = true")])
        self.assertEqual(actions, ["stop-begin", "stop-end"])

    def test_two_cycles_reset_stop_completion_state(self):
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "GameMode._manualActive = false"),
                                (4500, "GameMode._manualActive = true"),
                                (5600, "GameMode._manualActive = false")], finish=8700)
        self.assertEqual(actions, ["stop-begin", "stop-end", "start-process",
                                   "stop-begin", "stop-end", "start-process"])

    def test_nothing_stopped_never_starts_or_retries_forever(self):
        self.executable("pgrep", '''printf 'probe-empty\n' >> "$HOME/actions.log"; exit 1''')
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (3000, "GameMode._manualActive = false")])
        self.assertEqual(actions, ["probe-empty"])

    def test_multiple_toggles_during_stop_restore_once(self):
        actions = self.run_qml([(400, "GameMode._manualActive = true"),
                                (1500, "GameMode._manualActive = false"),
                                (1800, "GameMode._manualActive = true"),
                                (2100, "GameMode._manualActive = false")])
        self.assertEqual(actions, ["stop-begin", "stop-end", "start-process"])

    def test_install_probe_completion_reconciles_already_active_mode(self):
        path = self.base / "services/GameMode.qml"
        # Delay only the external probe, not its production exit callback.
        path.write_text(path.read_text().replace('"command -v discover-overlay >/dev/null"',
                                                '"sleep 1.2; command -v discover-overlay >/dev/null"'))
        actions = self.run_qml([(400, "GameMode._manualActive = true")], finish=4800)
        self.assertEqual(actions, ["stop-begin", "stop-end"])

    def test_absent_overlay_does_nothing(self):
        (self.base / "bin/discover-overlay").unlink()
        # Probe with an explicit fixture-only PATH so an installed host binary cannot leak in.
        path = self.base / "services/GameMode.qml"
        path.write_text(path.read_text().replace('"command -v discover-overlay >/dev/null"',
                                                '"PATH=\\\"$HOME/bin\\\"; command -v discover-overlay >/dev/null"'))
        actions = self.run_qml([(400, "GameMode._manualActive = true")], finish=1500)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()