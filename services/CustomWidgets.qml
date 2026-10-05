pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common
import qs.modules.common.functions

Singleton {
    id: root

    // Discovered custom widgets: [{ id, name, icon, qmlPath, dirPath, ... }]
    property list<var> widgets: []
    readonly property bool ready: _scanDone
    readonly property string widgetsDir: `${Directories.shellConfig}/widgets`

    property bool _scanDone: false

    Component.onCompleted: _scan()
    Connections {
        target: Config
        function onReadyChanged() {
            root._seedMissingConfig();
        }
        function onCustomWidgetDataSyncedChanged() {
            root._seedMissingConfig();
        }
    }

    function reload(): void {
        root._scanDone = false;
        root.widgets = [];
        _scan();
    }

    function _scan(): void {
        _scanProcess.running = true;
    }

    // Single process that finds and reads all manifests, outputs JSON array
    Process {
        id: _scanProcess
        command: [Directories.scriptsPath + "/scan-widgets.sh", root.widgetsDir]
        running: false

        stdout: StdioCollector {
            id: _scanCollector
            onStreamFinished: {
                const output = (_scanCollector.text ?? "").trim();
                root._parseResults(output || "[]");
            }
        }

        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0 && !root._scanDone) {
                root._scanDone = true;
            }
        }
    }

    // Validate manifest fields, returns array of warning strings (empty = valid)
    function _validateManifest(id: string, m: var, dir: string): list<string> {
        const warnings = [];
        if (!m.name) warnings.push(`${id}: missing "name" field`);
        if (!m.version) warnings.push(`${id}: missing "version" field`);
        const qmlFile = m.main || (id.charAt(0).toUpperCase() + id.slice(1) + ".qml");
        // configKeys type validation
        if (m.configKeys && typeof m.configKeys === "object") {
            for (const key in m.configKeys) {
                const spec = m.configKeys[key];
                const validTypes = ["int", "real", "bool", "string"];
                if (spec.type && validTypes.indexOf(spec.type) < 0)
                    warnings.push(`${id}: configKey "${key}" has unknown type "${spec.type}"`);
            }
        }
        return warnings;
    }

    function _parseResults(jsonStr: string): void {
        try {
            const entries = JSON.parse(jsonStr);
            const result = [];
            for (const entry of entries) {
                const m = entry.manifest;
                const warnings = root._validateManifest(entry.id, m, entry.dir);
                if (warnings.length > 0)
                    console.warn("[CustomWidgets]", warnings.join("; "));
                const qmlFile = m.main || (entry.id.charAt(0).toUpperCase() + entry.id.slice(1) + ".qml");
                const iris = m.iris && typeof m.iris === "object" ? m.iris : {};
                const irisFile = typeof iris.main === "string" ? iris.main.trim() : "";
                result.push({
                    id: entry.id,
                    name: m.name || entry.id,
                    icon: m.icon || "widgets",
                    version: m.version || "1.0",
                    author: m.author || "",
                    description: m.description || "",
                    category: m.category || "",
                    qmlPath: `file://${entry.dir}/${qmlFile}`,
                    irisQmlPath: irisFile.length > 0 ? `file://${entry.dir}/${irisFile}` : "",
                    irisSlots: Array.isArray(iris.slots) ? iris.slots : [],
                    dirPath: entry.dir,
                    configKeys: m.configKeys || {},
                    resizableAxes: m.resizableAxes || {},
                    defaultSize: m.defaultSize || { width: 200, height: 100 },
                    defaultConfig: m.defaultConfig || {},
                    valid: warnings.length === 0,
                    warnings: warnings
                });
            }
            root.widgets = result;
        } catch (e) {
            console.warn("[CustomWidgets] Failed to parse manifests:", e);
        }
        root._scanDone = true;
        root._seedMissingConfig();
    }

    function _readCustomConfig(widgetId: string, key: string): var {
        return Config.getNestedValue("background.widgets.custom." + widgetId + "." + key, undefined);
    }

    function _defaultForSpec(spec: var): var {
        if (spec && spec.default !== undefined)
            return spec.default;
        const type = spec?.type ?? "bool";
        if (type === "bool") return false;
        if (type === "string") {
            if (spec?.options && spec.options.length > 0) {
                const first = spec.options[0];
                return (first && typeof first === "object") ? (first.value ?? first.label ?? first.displayName ?? "") : first;
            }
            return "";
        }
        return 0;
    }

    function _widgetDefaults(widget: var, index: int): var {
        let defaults = {
            enable: false,
            placementStrategy: "free",
            x: 240 + index * 36,
            y: 240 + index * 28,
            widgetScale: 100,
            widgetOpacity: 100,
            colorMode: "auto",
            dim: 0,
            backgroundOpacity: 0.06,
            borderWidth: 1,
            borderOpacity: 0.08,
            cornerRadius: -1
        };
        const axes = widget.resizableAxes || {};
        const size = widget.defaultSize || {};
        if (axes.width && size.width !== undefined) defaults[axes.width] = size.width;
        if (axes.height && size.height !== undefined) defaults[axes.height] = size.height;
        if (axes.uniform && axes.uniform !== "widgetScale" && size.width !== undefined)
            defaults[axes.uniform] = size.width;
        const extraDefaults = widget.defaultConfig || {};
        for (const key in extraDefaults)
            defaults[key] = extraDefaults[key];
        const configKeys = widget.configKeys || {};
        for (const key in configKeys)
            defaults[key] = root._defaultForSpec(configKeys[key]);
        return defaults;
    }

    function _seedMissingConfig(): void {
        if (!Config.ready || !Config.customWidgetDataSynced || !root._scanDone || root.widgets.length === 0)
            return;
        let updates = {};
        for (let i = 0; i < root.widgets.length; i++) {
            const widget = root.widgets[i];
            const defaults = root._widgetDefaults(widget, i);
            for (const key in defaults) {
                if (root._readCustomConfig(widget.id, key) === undefined)
                    updates["background.widgets.custom." + widget.id + "." + key] = defaults[key];
            }
        }
        if (Object.keys(updates).length > 0)
            Config.setNestedValues(updates);
    }

    // Get a custom widget's config value (freeform namespace)
    function getConfigValue(widgetId: string, key: string, defaultValue: var): var {
        return Config.getNestedValue("background.widgets.custom." + widgetId + "." + key, defaultValue);
    }

    // Set a custom widget's config value
    function setConfigValue(widgetId: string, key: string, value: var): void {
        Config.setNestedValue("background.widgets.custom." + widgetId + "." + key, value);
    }

    // Create a new widget from template
    function create(name: string): void {
        if (!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(name)) return;
        _createProcess.widgetName = name;
        _createProcess.running = true;
    }

    // Delete a widget by removing its directory
    function remove(widgetId: string): void {
        if (!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(widgetId)) return;
        _removeProcess.widgetId = widgetId;
        _removeProcess.running = true;
    }

    // Install the built-in example widget
    function installExample(): void {
        _installExampleProcess.running = true;
    }

    // Open widget directory in file manager
    function openWidgetDir(widgetId: string): void {
        if (widgetId && !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(widgetId)) return;
        const dirPath = widgetId ? `${root.widgetsDir}/${widgetId}` : root.widgetsDir;
        Qt.openUrlExternally("file://" + dirPath);
    }

    // Widget template generator — creates scaffold with all imports, services, and patterns
    Process {
        id: _createProcess
        property string widgetName: ""
        running: false
        command: ["python3", Directories.scriptsPath + "/widgets/manage.py", "create",
            root.widgetsDir, _createProcess.widgetName]
        stdout: StdioCollector {
            onStreamFinished: root.reload()
        }
    }

    // Remove a widget directory
    Process {
        id: _removeProcess
        property string widgetId: ""
        running: false
        command: ["python3", Directories.scriptsPath + "/widgets/manage.py", "remove",
            root.widgetsDir, _removeProcess.widgetId]
        stdout: StdioCollector {
            onStreamFinished: root.reload()
        }
    }

    // Copy example widget from defaults
    Process {
        id: _installExampleProcess
        running: false
        command: ["python3", Directories.scriptsPath + "/widgets/manage.py", "example",
            root.widgetsDir, "example-widget"]
        stdout: StdioCollector {
            onStreamFinished: root.reload()
        }
    }
}
