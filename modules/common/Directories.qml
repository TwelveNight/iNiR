pragma Singleton
pragma ComponentBehavior: Bound

import qs.modules.common.functions
import qs.services
import QtCore
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    // XDG Dirs, with "file://"
    readonly property string home: StandardPaths.standardLocations(StandardPaths.HomeLocation)[0]
    readonly property string config: StandardPaths.standardLocations(StandardPaths.ConfigLocation)[0]
    readonly property string state: "file://" + (Quickshell.env("INIR_STATE_DIR") || `${Quickshell.env("XDG_STATE_HOME") || (homePath + "/.local/state")}/inir`)
    readonly property string cache: "file://" + (Quickshell.env("XDG_CACHE_HOME") || (homePath + "/.cache")) + "/inir"
    readonly property string genericCache: StandardPaths.standardLocations(StandardPaths.GenericCacheLocation)[0]
    readonly property string documents: StandardPaths.standardLocations(StandardPaths.DocumentsLocation)[0]
    readonly property string downloads: StandardPaths.standardLocations(StandardPaths.DownloadLocation)[0]
    readonly property string pictures: StandardPaths.standardLocations(StandardPaths.PicturesLocation)[0]
    readonly property string music: StandardPaths.standardLocations(StandardPaths.MusicLocation)[0]
    readonly property string videos: StandardPaths.standardLocations(StandardPaths.MoviesLocation)[0]
    readonly property string homePath: FileUtils.trimFileProtocol(home)
    readonly property string configPath: FileUtils.trimFileProtocol(config)
    readonly property string statePath: FileUtils.trimFileProtocol(state)
    readonly property string cachePath: FileUtils.trimFileProtocol(cache)
    // Runtime files must not collide with II (fallback remains private to this user).
    readonly property string tempPath: Quickshell.env("XDG_RUNTIME_DIR")
        ? Quickshell.env("XDG_RUNTIME_DIR") + "/inir" : cachePath + "/tmp"
    readonly property string genericCachePath: FileUtils.trimFileProtocol(genericCache)
    readonly property string documentsPath: FileUtils.trimFileProtocol(documents)
    readonly property string downloadsPath: FileUtils.trimFileProtocol(downloads)
    readonly property string picturesPath: FileUtils.trimFileProtocol(pictures)
    readonly property string musicPath: FileUtils.trimFileProtocol(music)
    readonly property string videosPath: FileUtils.trimFileProtocol(videos)

    // Other dirs used by the shell, without "file://"
    property string assetsPath: Quickshell.shellPath("assets")
    property string scriptPath: Quickshell.shellPath("scripts")
    property string scriptsPath: FileUtils.trimFileProtocol(scriptPath)
    property string stateUserPath: `${Directories.statePath}/user`
    // Palette files are intentionally shared with Hyprland + II.
    readonly property string sharedGeneratedPath: `${Quickshell.env("XDG_STATE_HOME") || (homePath + "/.local/state")}/quickshell/user/generated`
    property string wallpapersPath: Config.options?.wallpapers?.directory || `${Directories.picturesPath}/Wallpapers`
    property string screenshotsPath: Config.options?.regionSelector?.savePath || `${Directories.picturesPath}/Screenshots`
    property string persistentStatesPath: `${Directories.statePath}/states.json`
    property string eventsPath: `${Directories.stateUserPath}/events.json`
    property string screenTimePath: `${Directories.stateUserPath}/screentime`
    property string generatedMaterialScssPath: `${Directories.sharedGeneratedPath}/material_colors.scss`
    property string favicons: `${Directories.cachePath}/media/favicons`
    // User avatar paths
    property string userAvatarPathAccountsService: FileUtils.trimFileProtocol(`/var/lib/AccountsService/icons/${SystemInfo.username}`)
    property string userAvatarPathRicersAndWeirdSystems: `${Directories.homePath}/.face`
    property string userAvatarPathRicersAndWeirdSystems2: `${Directories.homePath}/.face.icon`
    property int userAvatarRevision: 0

    FileView {
        id: avatarAccountsProbe
        path: root.userAvatarPathAccountsService
        watchChanges: true
        printErrors: false
        onFileChanged: root.userAvatarRevision++
    }

    FileView {
        id: avatarFaceProbe
        path: root.userAvatarPathRicersAndWeirdSystems
        watchChanges: true
        printErrors: false
        onFileChanged: root.userAvatarRevision++
    }

    FileView {
        id: avatarFaceIconProbe
        path: root.userAvatarPathRicersAndWeirdSystems2
        watchChanges: true
        printErrors: false
        onFileChanged: root.userAvatarRevision++
    }

    readonly property var userAvatarPaths: [
        avatarAccountsProbe.loaded ? userAvatarPathAccountsService : "",
        avatarFaceProbe.loaded ? userAvatarPathRicersAndWeirdSystems : "",
        avatarFaceIconProbe.loaded ? userAvatarPathRicersAndWeirdSystems2 : ""
    ].filter(path => String(path ?? "").trim().length > 0)
    readonly property string userAvatarSourcePrimary: avatarSourceAt(0)

    onUserAvatarRevisionChanged: {
        avatarAccountsProbe.reload()
        avatarFaceProbe.reload()
        avatarFaceIconProbe.reload()
    }
    property string coverArt: `${Directories.cachePath}/media/coverart`
    property string tempImages: `${Directories.tempPath}/media/images`
    property string booruPreviews: `${Directories.cachePath}/media/boorus`
    property string booruDownloads: Config.options?.sidebar?.booru?.downloadPath?.sfw || Directories.wallpapersPath
    property string booruDownloadsNsfw: Config.options?.sidebar?.booru?.downloadPath?.nsfw || `${Directories.wallpapersPath}/🌶️`
    property string latexOutput: `${Directories.cachePath}/media/latex`
    property string shellConfig: Quickshell.env("INIR_CONFIG_DIR") || `${Directories.configPath}/inir`
    property string shellConfigName: "config.json"
    property string shellConfigPath: `${Directories.shellConfig}/${Directories.shellConfigName}`
    property string updateLogPath: `${Directories.stateUserPath}/update.log`
    property string updateStatusPath: `${Directories.stateUserPath}/update-status`
    property string todoPath: `${Directories.stateUserPath}/todo.json`
    property string todoTxtPath: `${Directories.stateUserPath}/todo.txt`
    property string notepadPath: `${Directories.stateUserPath}/notepad.txt`
    property string notesPath: `${Directories.stateUserPath}/notes.txt`
    property string conflictCachePath: `${Directories.cachePath}/conflict-killer`
    // Both shells serialize the same notification-history fields.
    property string notificationsPath: `${Quickshell.env("XDG_CACHE_HOME") || (homePath + "/.cache")}/quickshell/notifications/notifications.json`
    property string calendarSyncCachePath: `${Directories.stateUserPath}/calendar-sync-cache.json`
    property string weatherCachePath: `${Directories.stateUserPath}/weather-cache.json`
    property string generatedMaterialThemePath: `${Directories.sharedGeneratedPath}/colors.json`
    property string generatedPalettePath: `${Directories.sharedGeneratedPath}/palette.json`
    property string generatedAppPalettePath: `${Directories.sharedGeneratedPath}/app-palette.json`
    property string generatedTerminalPalettePath: `${Directories.sharedGeneratedPath}/terminal.json`
    property string generatedThemeMetaPath: `${Directories.sharedGeneratedPath}/theme-meta.json`
    property string generatedChromiumThemePath: `${Directories.sharedGeneratedPath}/chromium.theme`
    property string generatedWallpaperCategoryPath: `${Directories.sharedGeneratedPath}/wallpaper/category.txt`
    property string cliphistDecode: `${Directories.tempPath}/media/cliphist`
    property string screenshotTemp: `${Directories.tempPath}/media/screenshot`
    property string wallpaperSwitchScriptPath: `${Directories.scriptsPath}/colors/switchwall.sh`
    property string defaultAiPrompts: Quickshell.shellPath("defaults/ai/prompts")
    property string userAiPrompts: FileUtils.trimFileProtocol(`${Directories.shellConfig}/ai/prompts`)
    property string userActions: FileUtils.trimFileProtocol(`${Directories.shellConfig}/actions`)
    property string aiChats: `${Directories.stateUserPath}/ai/chats`
    property string aiTranslationScriptPath: `${Directories.scriptsPath}/ai/gemini-translate.sh`
    property string recordScriptPath: `${Directories.scriptsPath}/videos/record.sh`

    function shortHomePath(path: string): string {
        const cleaned = FileUtils.trimFileProtocol(path)
        if (cleaned === root.homePath)
            return "~"
        if (cleaned.startsWith(root.homePath + "/"))
            return "~" + cleaned.slice(root.homePath.length)
        return cleaned
    }

    function avatarSourceAt(index: int): string {
        if (index < 0 || index >= userAvatarPaths.length)
            return ""

        const path = String(userAvatarPaths[index] ?? "").trim()
        return path.length > 0 ? `file://${path}?inir-avatar=${root.userAvatarRevision}` : ""
    }

    function nextAvatarSource(currentSource: string): string {
        const normalized = String(currentSource ?? "")
            .replace(/^file:\/\//, "")
            .replace(/\?inir-avatar=\d+$/, "")

        for (let i = 0; i < userAvatarPaths.length; ++i) {
            if (String(userAvatarPaths[i] ?? "") === normalized)
                return avatarSourceAt(i + 1)
        }

        return userAvatarSourcePrimary
    }
    // Cleanup on init
    Component.onCompleted: {
        Quickshell.execDetached(["mkdir", "-p", tempPath])
        Quickshell.execDetached(["mkdir", "-p", `${shellConfig}`])
        Quickshell.execDetached(["mkdir", "-p", `${stateUserPath}`])
        Quickshell.execDetached(["mkdir", "-p", `${favicons}`])
        Quickshell.execDetached(["mkdir", "-p", `${coverArt}`])
        Quickshell.execDetached(["rm", "-rf", `${booruPreviews}`])
        Quickshell.execDetached(["mkdir", "-p", `${booruPreviews}`])
        Quickshell.execDetached(["rm", "-rf", `${latexOutput}`])
        Quickshell.execDetached(["mkdir", "-p", `${latexOutput}`])
        Quickshell.execDetached(["rm", "-rf", `${cliphistDecode}`])
        Quickshell.execDetached(["mkdir", "-p", `${cliphistDecode}`])
        Quickshell.execDetached(["mkdir", "-p", `${aiChats}`])
        Quickshell.execDetached(["mkdir", "-p", `${screenTimePath}`])
        Quickshell.execDetached(["mkdir", "-p", `${userActions}`])
        Quickshell.execDetached(["rm", "-rf", `${tempImages}`])
    }
}
