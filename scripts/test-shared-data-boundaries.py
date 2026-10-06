#!/usr/bin/env python3
"""Exercise real QML persistence against synthetic data and a mock keyring only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SharedDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-shared-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for folder in ["modules/common/functions", "services", "runtime", "bin",
                       "config/illogical-impulse", "config/inir", "state/inir/user",
                       "state/quickshell/user/generated", "cache/quickshell/notifications"]:
            (self.base / folder).mkdir(parents=True)
        (self.base / "runtime").chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.base), QT_QPA_PLATFORM="offscreen",
                        XDG_CONFIG_HOME=str(self.base / "config"), XDG_STATE_HOME=str(self.base / "state"),
                        XDG_CACHE_HOME=str(self.base / "cache"), XDG_DATA_HOME=str(self.base / "data"),
                        XDG_RUNTIME_DIR=str(self.base / "runtime"), INIR_STANDALONE_WINDOW="1",
                        INIR_CONFIG_DIR=str(self.base / "config/inir"), INIR_STATE_DIR=str(self.base / "state/inir"),
                        PATH=str(self.base / "bin") + ":" + os.environ["PATH"])
        self.ii_config = self.base / "config/illogical-impulse/config.json"
        self.ii_config.write_text('{"appearance":{"globalStyle":"II-sentinel"}}')
        self.ii_original = self.ii_config.read_bytes()
        (self.base / "config/inir/config.json").write_text('{"appearance":{"theme":"auto","globalStyle":"material"}}')
        (self.base / "state/inir/user/todo.json").write_text('[{"content":"private task","done":false}]')
        self.ii_todo = self.base / "state/quickshell/user/todo.json"
        self.ii_todo.write_text('[{"id":"II-id","content":"II task","done":false,"date":42}]')
        self.palette = self.base / "state/quickshell/user/generated/colors.json"
        self.palette.write_text('{"background":"#112233","primary":"#778899","darkmode":true,"transparent":true}')
        (self.palette.parent / "theme-meta.json").write_text('{}')
        self.history = self.base / "cache/quickshell/notifications/notifications.json"
        self.history_value = [{"notificationId": 42, "actions": [], "appIcon": "icon", "appName": "fixture",
                               "body": "synthetic body", "image": "", "summary": "synthetic title", "time": 1234,
                               "urgency": "normal"}]
        self.history.write_text(json.dumps(self.history_value))
        for file in ["modules/common/Directories.qml", "modules/common/Config.qml", "services/Todo.qml",
                     "services/MaterialThemeLoader.qml", "services/Notifications.qml", "services/FontSyncService.qml"]:
            self.copy_singleton(file)
        self.copy_singleton("services/deferred/KeyringStorage.qml", "services/KeyringStorage.qml")
        self.stub("modules/common/functions", "FileUtils", r'function trimFileProtocol(p) { return String(p).replace(/^file:\/\//, "") }')
        self.stub("modules/common", "Appearance", '''property QtObject m3colors: QtObject {
            property color m3background: "#000000"; property color m3primary: "#000000"
            property bool darkmode: false; property bool transparent: false
        }''')
        self.stub("modules/common", "Translation", 'function tr(s) { return s }')
        self.stub("services", "SystemInfo", 'property string username: "inir-fixture-no-such-user"')
        self.stub("services", "ThemeService", 'property string appsSurfaceSeed: ""')
        self.stub("services", "GameMode", 'property bool active: false; property bool suppressNotifications: false')
        self.stub("services", "DateTime", 'property var clock: ({date: new Date()})')
        self.stub(".", "GlobalStates", '''property bool windowPreviewCaptureActive: false
            property bool sidebarRightOpen: false; property bool waffleNotificationCenterOpen: false''')
        for file in ["keyring/try_lookup.sh", "keyring/is_unlocked.sh", "lib/config-path.sh"]:
            target = self.base / "scripts" / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "scripts" / file, target)
        font_sync = self.base / "scripts/colors/sync-system-fonts.sh"
        font_sync.parent.mkdir(parents=True)
        font_sync.write_text('#!/bin/sh\nprintf "unexpected\\n" > "$HOME/font-sync-called"\n')
        font_sync.chmod(0o755)
        self.env["MOCK_KEYRING_DATA"] = str(self.base / "keyring.json")
        self.env["MOCK_KEYRING_SAVES"] = str(self.base / "saves.log")
        self.env["MOCK_KEYRING_MODE"] = "valid"
        (self.base / "keyring.json").write_text('{"apiKeys":{"gemini":"fixture-old"},"otherProvider":{"token":"fixture-only"}}')
        self.executable("secret-tool", '''#!/bin/sh
case "$1" in
lookup)
    [ "$2 $3" = "application illogical-impulse" ] || exit 9
    case "$MOCK_KEYRING_MODE" in
        missing|locked) exit 1 ;;
        error) echo 'fixture lookup error' >&2; exit 1 ;;
        malformed) printf '{invalid'; exit 0 ;;
    esac
    cat "$MOCK_KEYRING_DATA" ;;
store)
    printf 'save\\n' >> "$MOCK_KEYRING_SAVES"
    cat > "$MOCK_KEYRING_DATA" ;;
*) exit 9 ;;
esac
''')
        # Persistence tests use a synthetic status backend, never the real bus.
        # The real helper is covered by test-login-keyring.py on a private bus.
        (self.base / "scripts/keyring/login-keyring.py").write_text(
            "import os, sys\nsys.exit(1 if os.environ['MOCK_KEYRING_MODE'] == 'locked' else 0)\n")

    def copy_singleton(self, source, destination=None):
        dest = self.base / (destination or source)
        shutil.copy2(ROOT / source, dest)
        with (dest.parent / "qmldir").open("a") as f:
            f.write(f"singleton {dest.stem} 1.0 {dest.name}\n")

    def stub(self, folder, name, body):
        dest = self.base / folder
        (dest / f"{name}.qml").write_text(f"pragma Singleton\nimport QtQuick\nQtObject {{\n{body}\n}}\n")
        with (dest / "qmldir").open("a") as f:
            f.write(f"singleton {name} 1.0 {name}.qml\n")

    def executable(self, name, contents):
        p = self.base / "bin" / name
        p.write_text(contents)
        p.chmod(0o755)

    def qml(self, startup, check, after="", delay=700):
        (self.base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.modules.common
import qs.services
ShellRoot {
    function verify(ok, message) { if (!ok) throw new Error("FAIL " + message) }
    Component.onCompleted: { STARTUP }
    Timer { running: true; interval: DELAY; onTriggered: {
        try {
            CHECK
            finish.start()
        } catch (e) { console.error(String(e)); Qt.quit() }
    } }
    Timer { id: finish; interval: 800; onTriggered: {
        try {
            AFTER
            console.log("PASS shared data boundaries")
        } catch (e) { console.error(String(e)) }
        Qt.quit()
    } }
}
'''.replace("STARTUP", startup).replace("DELAY", str(delay)).replace("CHECK", check).replace("AFTER", after))
        result = subprocess.run(["dbus-run-session", "--", "qs", "-p", str(self.base), "--no-color"],
                                env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
        self.assertIn("PASS shared data boundaries", result.stdout, result.stdout)
        for error in ["FAIL ", "ReferenceError", "TypeError", "Failed to load configuration"]:
            self.assertNotIn(error, result.stdout, result.stdout)
        self.assertEqual(self.ii_config.read_bytes(), self.ii_original)

    def test_style_and_todo_are_private_palette_colors_are_shared(self):
        original_todo = self.ii_todo.read_bytes()
        self.qml('Config.ready; Todo.list; MaterialThemeLoader.ready; FontSyncService.syncEnabled;', '''
            verify(Config.ready, "config did not load")
            verify(Directories.shellConfig === Quickshell.env("INIR_CONFIG_DIR"), "config override")
            Config.setNestedValue("appearance.globalStyle", "cards")
            Config.setNestedValue("bar.bottom", true)
            Config.setNestedValue("appearance.typography.mainFont", "Fixture Font")
            verify(!FontSyncService.syncEnabled, "shell font sync touches shared system settings")
            Config.flushWrites()
            Todo.markDone(0)
            Appearance.m3colors.transparent = true
            MaterialThemeLoader.applyColors(JSON.stringify({background:"#112233", primary:"#abcdef", transparent:true, darkmode:true}))
            verify(Appearance.m3colors.m3primary.toString() === "#abcdef", "color not shared")
            verify(!Appearance.m3colors.transparent, "shared transparent flag leaked")
            Config.setNestedValue("appearance.theme", "custom")
            Appearance.m3colors.transparent = true
            MaterialThemeLoader._forceApply = true
            MaterialThemeLoader.applyColors(JSON.stringify({background:"#112233", primary:"#abcdef", transparent:false}))
            verify(Appearance.m3colors.transparent, "local preset transparency overwritten")
            Config.flushWrites()
        ''')
        config = json.loads((self.base / "config/inir/config.json").read_text())
        self.assertEqual(config["appearance"]["globalStyle"], "cards")
        self.assertEqual(config["bar"]["bottom"], True)
        self.assertEqual(self.ii_todo.read_bytes(), original_todo)
        self.assertFalse((self.base / "font-sync-called").exists())
        self.assertTrue(json.loads((self.base / "state/inir/user/todo.json").read_text())[0]["done"])

    def test_icon_startup_reads_shared_choice_without_restoring_private_setting(self):
        self.copy_singleton("services/IconThemeService.qml")
        icon_service = self.base / "services/IconThemeService.qml"
        # Substitute only the executable path; keep production lifecycle logic.
        icon_service.write_text(icon_service.read_text().replace('"/usr/bin/gsettings"', '"gsettings"'))
        self.executable("gsettings", '''#!/bin/sh
printf '%s\\n' "$*" >> "$HOME/icon-settings.log"
[ "$1" = get ] || exit 9
printf "'Shared Fixture Icons'\\n"
''')
        (self.base / "config/inir/config.json").write_text('{"appearance":{"iconTheme":"Stale Private Icons"}}')
        self.qml('Config.ready; IconThemeService.ensureInitialized();', '''
            verify(IconThemeService.currentTheme === "Shared Fixture Icons", "shared icon choice was not read")
            verify(Config.options.appearance.iconTheme === "Stale Private Icons", "private setting was unexpectedly rewritten")
        ''')
        self.assertEqual((self.base / "icon-settings.log").read_text().splitlines(),
                         ["get org.gnome.desktop.interface icon-theme"])

    def test_niri_nightlight_controls_only_its_owned_service(self):
        self.copy_singleton("services/Hyprsunset.qml")
        self.stub("services", "CompositorService", 'property bool isNiri: true')
        (self.base / "services/DateTime.qml").write_text('''pragma Singleton
import QtQuick
QtObject { property var clock: ({hours: 12, minutes: 0, date: new Date()}) }
''')
        service = self.base / "services/Hyprsunset.qml"
        text = service.read_text()
        for name in ["systemctl", "systemd-run", "pkill", "pidof"]:
            # Keep every production command argument, using fixture executables.
            text = text.replace(f"/usr/bin/{name}", str(self.base / "bin" / name))
            self.executable(name, f'''#!/bin/sh
printf '{name} %s\\n' "$*" >> "$HOME/nightlight-actions.log"
case "$*" in *is-active*) exit 1;; esac
exit 0
''')
        service.write_text(text)
        self.qml('Config.ready; Hyprsunset.load();', 'Hyprsunset.enable();',
                 'verify(Hyprsunset.active, "nightlight did not enable"); Hyprsunset.disable();')
        actions = (self.base / "nightlight-actions.log").read_text()
        self.assertIn("systemctl --user is-active --quiet inir-wlsunset.service", actions)
        self.assertIn("systemctl --user stop inir-wlsunset.service", actions)
        self.assertIn("--unit=inir-wlsunset.service --property=PartOf=niri.service", actions)
        self.assertNotIn("pkill ", actions)
        self.assertNotIn("pidof ", actions)

    def test_keyring_edits_preserve_other_provider_fields_and_queue_saves(self):
        self.qml('KeyringStorage.fetchKeyringData();', '''
            verify(KeyringStorage.loaded, "keyring not loaded")
            KeyringStorage.setNestedField(["apiKeys", "gemini"], "fixture-new")
            KeyringStorage.setNestedField(["apiKeys", "openai"], "fixture-second")
        ''')
        value = json.loads((self.base / "keyring.json").read_text())
        self.assertEqual(value["otherProvider"], {"token": "fixture-only"})
        self.assertEqual(value["apiKeys"], {"gemini": "fixture-new", "openai": "fixture-second"})

    def test_keyring_failed_reads_never_save_empty_data(self):
        for mode in ["malformed", "locked", "error"]:
            with self.subTest(mode=mode):
                self.env["MOCK_KEYRING_MODE"] = mode
                before = (self.base / "keyring.json").read_bytes()
                self.qml('KeyringStorage.fetchKeyringData();', '''
                    verify(!KeyringStorage.loaded, "unsafe storage marked ready")
                    KeyringStorage.setNestedField(["apiKeys", "gemini"], "must-not-save")
                    KeyringStorage.saveKeyringData()
                ''')
                self.assertFalse((self.base / "saves.log").exists())
                self.assertEqual((self.base / "keyring.json").read_bytes(), before)

    def test_missing_keyring_entry_only_created_on_explicit_edit(self):
        self.env["MOCK_KEYRING_MODE"] = "missing"
        self.qml('KeyringStorage.fetchKeyringData();', 'verify(KeyringStorage.loaded, "missing entry not editable")')
        self.assertFalse((self.base / "saves.log").exists())
        self.qml('KeyringStorage.fetchKeyringData();', 'KeyringStorage.setNestedField(["apiKeys", "gemini"], "fixture-created")')
        self.assertEqual(json.loads((self.base / "keyring.json").read_text()), {"apiKeys": {"gemini": "fixture-created"}})

    def test_notifications_read_and_write_native_history(self):
        self.qml('Notifications.ensureInitialized();', '''
            verify(Notifications._historyWritable, "history not writable")
            verify(Notifications.list.length === 1 && Notifications.list[0].notificationId === 42, "history not shared")
            verify(Notifications.idOffset === 42, "history ID offset")
            Notifications.saveHistory()
        ''')
        self.assertEqual(json.loads(self.history.read_text()), self.history_value)

    def test_incompatible_notification_history_is_not_overwritten(self):
        for value in ['{invalid', json.dumps([dict(self.history_value[0], futureField="keep")])]:
            with self.subTest(value=value):
                self.history.write_text(value)
                self.qml('Notifications.ensureInitialized();', '''
                    verify(!Notifications._historyWritable, "incompatible history became writable")
                    Notifications.discardAllNotifications()
                    Notifications.saveHistory()
                ''')
                self.assertEqual(self.history.read_text(), value)


if __name__ == "__main__":
    unittest.main()
