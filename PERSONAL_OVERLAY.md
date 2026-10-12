# night/personal-overlay

本分支基于 `origin/prerelease` 的 `db2233ce`，用于 Night 的 Hyprland + II / Niri + iNiR 双会话。
本分支包含私有配置、共享 skwd-wall 与 GDM 安装适配。

## 路径与共享范围

| 内容 | 默认路径 | 归属 |
| --- | --- | --- |
| iNiR Shell 代码 | `~/.config/quickshell/inir` | iNiR |
| 设置、插件、凭据文件、版本、安装标记、Matugen 模板输入 | `~/.config/inir` | iNiR，支持 `INIR_CONFIG_DIR` |
| 待办、桌面布局、运行状态、更新备份 | `~/.local/state/inir` | iNiR，支持 `INIR_STATE_DIR` |
| Python 环境 | `~/.local/state/inir/.venv` | iNiR，支持 `INIR_VENV` |
| 图片与服务缓存 | `~/.cache/inir` | iNiR |
| 临时媒体、AI 请求、音乐播放器 socket | `$XDG_RUNTIME_DIR/inir`，无运行目录时为 `~/.cache/inir/tmp` | iNiR |
| 生成的调色板、终端颜色、应用配色元数据 | `~/.local/state/quickshell/user/generated` | 两边共享 |
| GTK、Qt、Kitty 等应用设置与配色 | 原有应用路径 | 保留个人基础设置；共享配色输出 |
| 壁纸渲染与活动状态 | `skwd-walld` / `skwd-helm` | 两边共享 |
| 通知历史 | `~/.cache/quickshell/notifications/notifications.json` | 两边共享相同 JSON 格式；通知显示/免打扰设置独立 |
| 剪贴板历史与 cliphist 设置 | cliphist 默认的 `~/.cache/cliphist/db`、`~/.config/cliphist/config` | 两边共享；删除、清空对两边生效 |
| 通用 API 密钥 | 系统钥匙环 `application=illogical-impulse` | 两边共享兼容 JSON 字段；保留其他服务字段 |
| YouTube OAuth、cookies 等专用登录文件 | `~/.config/inir` | II 没有对应实现，继续独立 |
| Niri 快捷键、启动项、规则 | `~/.config/niri` | 本次部署会安装 iNiR 的 Niri 配置 |

Shell 的布局、功能选项、字体、圆角、预设和插件独立，使用各自的 `config.json`。共享生成的配色和应用主题输出，但 iNiR 忽略共享调色板里的 `transparent` 样式标记；透明预设由自己的选择控制。Shell 字体默认不写入 GTK/KDE 的全局字体设置；`Apps use this font` 是手动开启的共享选项。

按“格式或读写方式不同就分开”的原则，待办继续使用 iNiR 私有 `todo.json` / `todo.txt`：II 有任务 ID、日期、完成历史与远程 provider，iNiR 的两向文本同步会丢掉额外字段，因此不合并、不转换 II 的任务。共享通用密钥也不意味着 iNiR 支持 II 的 TickTick/Google Tasks 登录和同步。

通知历史采用 II 当前的原生字段；发现损坏或额外未知字段时禁用本次进程的历史写入，保留原文件，当前通知仍可显示。钥匙环读取失败、格式损坏或锁定时禁止保存，确认条目不存在后也只在用户明确编辑时创建。两边依次登录使用；共享数据不提供两个 Shell 同时运行时的并发合并。
`Directories.qml` 是 QML 的路径入口；Shell 脚本使用 `scripts/lib/config-path.sh`，Python 使用 `scripts/lib/paths.py`。
没有整体覆盖 `XDG_CONFIG_HOME`，应用仍能读取已有配置。不会采用、迁移或链接 II 的 `illogical-impulse` 目录及安装标记。

## skwd-wall

桌面壁纸由 skwd-wall 负责。iNiR 的选择器通过安全的参数数组调用 `skwd-helm apply`，成功后才更新自己的设置。
`current --json` 提供权威活动状态；`watch` 事件触发合并查询，断开后重连，正常连接时不持续轮询。
桌面上的 QML 视频/GIF 渲染、awww 和 web renderer 已停用。选择器卡片、概览和锁屏仍可使用图片预览。
Waffle 的桌面选择也统一调用 skwd，桌面预览读取同一活动壁纸；独立锁屏与概览背景仍属于 Shell 表面。

沿用已有 `ii-skwd-wall-theme.service` 作为壁纸变更的配色生成者。iNiR 不因壁纸路径事件重复运行 Matugen。
iNiR 里主动选择配色、深浅模式或预设仍可写共享输出，后一次写入对两边生效。
两边的启动钩子调用 `scripts/personal/desktop-session.py`，确认真实合成器 IPC/Wayland socket 后，发布当前桌面的环境，清除另一桌面留下的身份和显卡变量，再重启 skwd-walld 与 II 的配色监听。壁纸内容、取色与数据库继续共享。

helper 用独立的 systemd 服务和 pidfd 监听合成器退出，无需轮询或依赖 Lua shutdown 钩子。Niri 使用临时 watcher；Hyprland 使用 `inir-hyprland-watch.service`，个人 target drop-in 将 `hyprland-session.target` 绑定到 watcher 的存活期。退出时停止旧 renderer/配色监听，清理对应会话环境；旧会话 watcher 不会停止已经接管的新会话。保留 skwd/II 配色服务的 default.target 启用关系，增加 `PartOf=graphical-session.target`，让标准 Niri 注销流程也能释放 renderer，下一次登录由相应桌面的 helper 重新启动。

安装器只从已有个人 Hyprland target 移除已知的 `PropagatesStopTo=graphical-session.target` 指令（systemd 依赖无法通过空 drop-in 清除），其他指令保留；由 `graphical-session.target` 的 `StopWhenUnneeded` 在最后一个 compositor 退出时停止图形服务。新的 Niri 会话已经接管时，清理残留 Hyprland target 不会停止它。`app-.service.d/40-desktop-ready.conf` 为 XDG 自启动应用增加就绪检查，仅在 Niri/Hyprland 生效：验证 compositor IPC 的真实 PID、Wayland socket 和本次 handoff 状态，最多等待 30 秒，超时不启动应用。systemd 在检查后重新读取主进程环境，避免 1Password、KDE Connect、输入法和托盘连接上一会话的显示地址；应用命令和 Portal 路由不变。其他普通应用服务和其他桌面不等待。
两套图形会话应依次切换，共享守护进程不提供同时登录两套桌面的隔离。

## GDM 与安装

保留 `/etc/systemd/system/display-manager.service -> gdm.service`。
直接使用已经安装的 `/usr/share/wayland-sessions/niri.desktop`，其中 `Exec=niri-session`。
GDM 登录时选择 **Niri**。标准入口通过 `niri.service` 启动；`inir.service` 仅挂在它的 wants 下，不随 Hyprland 启动。
不需要新增登录条目。`.deskto` 后缀的旧自定义条目通常不会被 GDM 识别。

Portal 按桌面分别配置：安装器备份并写入 `~/.config/xdg-desktop-portal/niri-portals.conf`，
让 Niri 的文件/目录选择、应用选择及设置读取使用 GTK 后端。
原有 `hyprland-portals.conf`、通用 `portals.conf` 和后端服务的 enable/mask 状态保持原样。
Niri 的屏幕共享/截图接口仍指定 GNOME 后端；若它被屏蔽，这些捕获接口需要另行配置，
不影响 GTK 文件选择器。当前会话更新路由后需重启 `xdg-desktop-portal.service`，新登录会自动读取。
文件/目录选择与“打开方式”等 portal 辅助窗口由独立的
`config.d/35-personal-window-rules.kdl` 设为浮动，初始尺寸为 960×700 逻辑像素。
安装器补齐这个规则层并保留后续个人编辑；原上游 `30-window-rules.kdl` 保持独立。
本机 Hyprland 的启动/退出钩子已经管理 `hyprland-session.target`。
若对应用户 unit 缺失，安装器补齐它与 `graphical-session.target` 的关联，
让停止会话时停止 portal；已有 unit 或 mask 不覆盖，不改原 Hyprland 钩子。
Niri 的标准 `niri-session` 入口会通过 `niri-shutdown.target` 停止图形会话。
Hyprland 的个人钩子 `custom/inir-session.lua` 由 `custom/execs.lua` 加载；安装器移除本机已知的两条异步环境导入命令，并在旧壁纸恢复脚本不存在时移除其调用，其他启动项不变。遇到未知环境导入钩子则停止部署，先人工审查。Niri 服务单独用 drop-in 清除继承的桌面/GPU 变量，再运行原来的 `niri --session`。

Docker Desktop 和 Sunshine 的用户服务取消自动启用，仍可手动启动；不修改 Docker Engine。个人安装器会保持这个启动策略，修改前备份原来的用户服务链接。
用户服务管理器的 linger 不妨碍这些会话服务停止，但 D-Bus 后续请求仍可能再次激活 portal。

无需修改 II 的 `installed_true`。它是存在性标记，不是布尔配置文件；iNiR 使用自己的标记。

部署入口（与官方命令一致，当前个人分支会自动进入隔离流程）：

依赖检查已扩展到锁屏兜底、音频/网络、钥匙环、Qt/QML 模块及私有 Python 的原生构建依赖。2026-10-05 重新核对发现本机缺少必需的 `swaylock`，需要补齐后再安装；此前较窄的预检通过不代表所有功能依赖齐全。安装前检查：

```sh
./setup install --check
./setup install -y
```

`--check` 不安装、不改配置；任何必需依赖或服务缺失都会中止。不要给 `./setup` 加 `sudo`。`-y` 取消逐项确认，可省略以逐项交互。保留当前个人分支工作区，不要重新 clone 上游来执行安装。

脚本先检查 skwd-helm、II 的配色监听脚本、标准 Niri 入口、GDM 和源码 Niri 配置。
在 `~/.local/state/inir/install-backups/<时间>-<pid>/` 保存现有 Niri 配置、iNiR 设置、Shell 代码、用户状态与服务链接，再通过内部标记运行 `./setup install --skip-deps --skip-setups` 的文件阶段，避免递归。
包装器沿用现有系统依赖，避免更换 II 使用的 Quickshell；安装阶段仍会创建 iNiR 私有 Python 环境。缺少依赖时先单独补齐。默认不替换应用基础配置、不改 Bash/Fish/Zsh 启动文件、不移除已有桌面包。
脚本结尾写入 Niri 和 systemd 的明确私有路径、把 iNiR 快捷键绑定到启动器绝对路径，并校验 Niri、服务 wants 链接、启动器和私有 Python 的必要模块。当前源码有效不等于实际 GDM 登录已通过。

## 回退与更新

首次安装备份中的 `config/niri` 是完整旧 Niri 目录，`runtime` 是旧 iNiR 代码，`inir-config` 是旧 iNiR 设置，`state/user` 是旧用户状态。
回退前先退出 Niri，停止 `inir.service`，再把对应目录及服务链接恢复到原位置并运行 `systemctl --user daemon-reload`。
备份中没有的路径表示安装前不存在；回退时只移除本次新建的对应 iNiR 路径。备份不会回退系统依赖包、共享配色、skwd 的活动壁纸。
卸载保留 II 状态、共享应用配置和调色板，也不自动恢复可能属于 II 的 `.old` 文件。

更新上游前先检查工作区并保存未提交修改。个人分支保持基于 `origin/prerelease`，后续更新需审查并解决个人补丁冲突。
已经部署后，使用 `inir update --local` 同步本地工作区；个人分支还没有远端对应分支，不要直接执行会拉取同名远端分支的普通更新。

### 合并 prerelease 后更新 live

对于当前 `repo-copy` 安装，从本仓库执行更新，不重新 clone，也不使用 `--realign` 或覆盖式安装：

```sh
cd /home/night/Template/github/niri-dots/iNiR
git status --short --branch
./setup install --check

# 自动更新快照只备份 Niri 的 config.kdl，不包括整套 config.d；额外保存完整目录。
backup="${INIR_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/inir}/manual-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a "${XDG_CONFIG_HOME:-$HOME/.config}/niri" "$backup/niri"
printf 'Niri backup: %s\n' "$backup/niri"

./setup update --local
niri validate --config "${XDG_CONFIG_HOME:-$HOME/.config}/niri/config.kdl"
inir version
```

`--local` 跳过远端拉取，把已经审查合并的代码同步到 `~/.config/quickshell/inir`，刷新启动器和已有服务，并执行迁移、重启 Shell。iNiR 的 `config.json` 不作为源码覆盖，但迁移可能改动指定字段或 Niri 启动项。更新不等同于复制整个 `defaults/niri`：其他 live Niri 个性层保持原样，新模板设置需另行按 include 链审查。

如果发现 runtime 本地修改，选择 **Preserve & Continue** 会先保存副本再安装新代码，不会自动把旧修改合并回来。副本在 `${INIR_STATE_DIR:-~/.local/state/inir}/user-mods/`；更新快照在同一状态目录的 `snapshots/`，最多保留 10 份。不要把“保存副本”理解为更新后仍应用旧文件。

更新失败时先保留日志。`./setup rollback` 会恢复快照，也可能对源码仓库执行 checkout/reset；自动快照中的 `commit_before` 在本地同步时取当前源码 HEAD，不一定是旧 live 的提交。回退前先保存源码工作区与分支，不把它当作完整 Niri/systemd 回退；整套 Niri 使用上面的额外备份。

上游迁移 044 停用安装器写入的已知外部 polkit 启动行，改用 Shell 内置认证窗口。已经运行的旧 agent 不会因此立刻退出，更新后应注销并重新登录 Niri。自定义 agent 启动脚本或个人额外配置不由该迁移删除。

### skwd-wall 与上游壁纸功能

个人分支仍由 `skwd-wall` 唯一绘制桌面，壁纸路径和显示器预览读取 daemon 的实际状态；不因上游新增 scaling/span/Afterglow 而启用第二个 QML/GIF/video 桌面渲染器。iNiR 的壁纸应用请求交给 `skwd-helm apply`，保留已有共享配色监听链路，避免重复取色。

Shell 的 `background.fillMode`、parallax 和桌面效果不等同于 skwd 的控制命令，因此相关设置按后端隐藏，缩放、播放和过渡在 skwd 设置中管理。Afterglow 的 Shell 外观仍保留，但壁纸调色选项在 skwd 模式明确只作用于 Shell 锁屏，不会改变 skwd 桌面。浏览器配色仅使用已有可写 policy 目录；不会自动提权、改权限或编辑真实浏览器 profile。

### Void / 非 systemd 上游兼容边界

同步上游 Void 支持时仍保留个人所有权边界：不因安装其他桌面包而删除 II，
不替换 GDM，不清理 II 的 Super-tap 服务，也不自动覆盖共享 GTK/终端基础设置。
`inir.service` 继续由 Niri 会话启动，不挂到用户 `default.target`。
Turnstile 的启动环境遵守已有 `INIR_VENV`，否则从 iNiR 私有状态目录解析 `.venv`。
Niri 夜灯仅控制 `inir-wlsunset.service`；没有可用 systemd 用户管理器时保持关闭，
不启动无归属的 `wlsunset`、不杀其他会话的进程。非 systemd 夜灯后端尚未接入个人层。

服务协调器在写入或清理前拒绝目标文件及父目录的符号链接别名，并把写入、权限
和启动配置更新失败传回安装器；systemd 模式不生成 iNiR 的 runit 启动文件。
Qt 6.11 的面板家族重启助手使用 `INIR_CONFIG_DIR` / 私有 iNiR 设置路径，不写 II；
GameMode 等待 Discover Overlay 停止完成后重新协调当前状态，避免切换期间遗漏恢复。
新安装的字体同步默认关闭，只有显式 opt-in 才应用系统字体同步。

Foot 的新生成文件为 `${XDG_CONFIG_HOME:-~/.config}/foot/inir-colors.ini`。
默认只更新颜色，不改现有 `foot.ini`；旧 `colors.ini` 仅在现有配置引用且带有生成器
标记时刷新，不迁移用户的 include，也不覆盖手写旧调色板。共享配置显式 opt-in
时才接入新 include。个人卸载保留 Foot 基础配置和新旧颜色文件。

## 触控板方向

`config.d/95-personal-input.kdl` 单独启用触控板 `natural-scroll`，与个人 Hyprland
习惯一致。由用户文件 `90-user-extra.kdl` 引入；不改 `10-input-and-cursor.kdl`，
也不改鼠标滚轮方向、光标样式或多指工作区手势。安装器保留此文件后续个人修改。

## 个人浮动窗口

`config.d/35-personal-window-rules.kdl` 同时迁移了
`~/.config/hypr/custom/rules.lua` 的个人浮动偏好：通讯软件、1Password、scrcpy、
音量/代理工具、指定 Brave 应用和 WPS。WPS 的字体、查找和替换窗口已由整个
WPS 应用匹配覆盖。Waydroid 初始尺寸为 540×960；Clash Verge、Sparkle、
Mihomo Party 为工作区宽度的 40%、高度的 60%。新浮动窗口使用 Niri 默认居中
位置；尺寸为逻辑像素/工作区比例，保留应用自身的尺寸约束。
Firefox Nightly 仅迁移初始尺寸，不额外强制浮动；Brave 空白窗口和 JetBrains
辅助窗口按原有标题限定，JetBrains 主窗口没有整体浮动规则。

浮动与初始尺寸规则在窗口创建时应用，热加载不会把已有窗口自动改为浮动。
`initial_title` 使用初次 configure 时的 `title` 匹配；若标题此后才到达，初始
属性不会重新应用。JetBrains 的 `no_focus` / `stay_focused` 仅映射为初始
不聚焦/聚焦，不保证整个窗口生命周期内禁止或锁定焦点。

`custom/hermes_pet.lua` 的 Hermes pet 只匹配独有标题 `Hermes Pet Overlay`，
迁移浮动和关闭装饰、阴影、模糊、失焦透明度。其标题变化后自动浮动逻辑、
`pin` 和 `no_follow_mouse` 无静态规则等价项，未模拟。没有为同名的 ChatGPT
主窗口和 pet 添加宽泛匹配。Vicinae 的 layer-shell 模糊属于图层效果，本次
浮动规则迁移不处理它。Hyprland 源配置保持原样。参考
[Niri 窗口规则](https://niri-wm.github.io/niri/Configuration%3A-Window-Rules.html)。

## Windows 游戏窗口与 Heroic

个人游戏规则放在 `config.d/96-personal-games.kdl`，由安装器接入
`90-user-extra.kdl`，后续保留用户编辑。上游窗口规则和 Heroic 启动器窗口保持独立。

明日方舟在当前 Heroic + Proton-CachyOS + Wine Wayland 组合下，主窗口实际
`app-id` 是 `steam_app_default`，标题是 `明日方舟`。它没有命中上游仅匹配
`steam_app_[0-9]+` / `wine` / `wine64` 的游戏规则。个人规则同时匹配主窗口的
身份和标题，移除游戏窗口的圆角裁剪、边框、阴影和
失焦透明度。另兼容 Wine/Xwayland 常见的 `Arknights.exe` 身份。
主窗口优先在 `HDMI-A-1` 外屏打开；目标输出不可用时由 Niri 回退到当前
可用输出。外屏为 2560×1440 / 100%，内屏为 2560×1600 / 125%
（逻辑尺寸 2048×1280）。实测从内屏启动后强制全屏会裁掉底部，
直接从外屏启动则正常，且用户确认全屏和流畅度恢复。因此优先在初次配置
窗口时选定外屏，避免启动后再强制拉伸。此输出规则已通过 Niri 校验；
从内屏发起启动时自动选外屏的行为尚未单独重启验证。
游戏自行控制全屏状态，不设置 `open-fullscreen`。

后续双屏复测仍出现窗口尺寸和平铺管理异常；上述规则只决定初始输出，不代表
双屏问题已解决。当前验收范围是**内屏关闭、仅外屏开启**，全屏和光标速度均已
由用户确认正常。Niri 专用 Xwayland 包装器对照已全部撤销，Heroic 的游戏设置
恢复原备份（Wine Wayland 开启、`wrapperOptions` 为空），实际进程重新加载
`winewayland.drv`。Heroic 会缓存游戏启动设置；恢复 JSON 后必须完整退出主进程
再启动，关闭窗口或留在托盘不足以确认回退生效。本次完整重启后光标迟缓消失。

游戏自身的显示模式也要设置为**全屏/无边框全屏**：Unity 保存的窗口模式会
产生带标题和关闭按钮的 Wine 窗口；只把窗口分辨率设为屏幕分辨率不会变成全屏。
2026-10-06 实测原有 `Screenmanager Fullscreen mode` 为 3（窗口模式），在游戏内
修改后为 1（无边框全屏），标题栏消失。优先通过游戏设置保存，不直接编辑
正在运行的 Wine 注册表，不为所有 Windows 程序强制全屏。

本机的 Heroic 游戏设置保留已经验证的组合：

| 设置 | 明日方舟当前值 |
| --- | --- |
| Runner | Proton-CachyOS-latest |
| Wine 原生 Wayland | 开启；实际加载 `winewayland.drv`，禁用 `winex11.drv` |
| NVIDIA PRIME | 开启；进程实际加载 NVIDIA Vulkan/GL 驱动 |
| DXVK / VKD3D | 沿用 Heroic 已有配置 |
| Gamescope / Gamescope 限帧 | 未启用 |
| MangoHud、额外帧率限制、HDR | 未启用 |
| 游戏文件、Wine prefix | 保留现有路径 |

不要为了全屏改系统级 `DISPLAY`、`WINEDLLOVERRIDES` 或强制所有游戏使用
同一种窗口后端；原生 Wine Wayland 不兼容的游戏可在 **Heroic 的单游戏设置**
关闭 Wine Wayland，经现有 xwayland-satellite 运行。需要固定渲染尺寸或嵌套
合成器的游戏再单独考虑 Gamescope，不因标题栏问题启用它。

新增游戏时先用 `niri msg windows` 核实主窗口 `app-id` 和标题，再在个人游戏文件
增加专用规则。多个 Proton sideload 可能共用 `steam_app_default`，不能只凭这个
身份把启动器、对话框和其他游戏全部全屏。参考
[Niri 窗口规则](https://niri-wm.github.io/niri/Configuration%3A-Window-Rules.html#open-fullscreen)
和 [Niri Xwayland 说明](https://niri-wm.github.io/niri/Xwayland.html)。

## 显示屏开关

“显示器 → 输出 → 显示屏开关”和“合成器 → 显示器”可单独开关连接的屏幕，
Waffle 的显示器设置也提供相同入口。关闭后仍保留列表入口，且禁止关闭最后一个活动屏幕。
操作使用 Niri IPC，只在当前会话生效，不写入 KDL，不改已保存的模式、缩放或位置；
重新登录或更改输出配置可能重置开关。窗口会按 Niri 的规则迁移到剩余屏幕。
此功能仅对 Niri 生效，不修改 Hyprland/II。

个人 `75-personal-binds.kdl` 为本机的 `eDP-2` 添加 `lid-open` 事件：开盖时清除
当前会话的关闭状态，不改模式、缩放和位置。合盖仍由 Niri 自己处理。
iRiS 的每个 Dock 独立持有窗口排序 lease，移除内屏 Dock 不再清空外屏的运行应用。
`python3 scripts/test-iris-dock-hotplug.py` 通过实际排序服务验证合盖、开盖、
外屏断开和最后一个 Dock 释放的行为。

### 显示器热插拔兼容（2026-10-06）

- `inir-output-wallpaper.service` 仅随 Niri 启停。输出变化稳定 3 秒后检查实际
  layer-shell 图层；只有缺失 skwd 壁纸图层的活动屏幕才按 daemon 当前保存的路径
  重新应用，保留其他屏幕的选择，不重启 skwd 服务。正常热插拔不重复重载壁纸。
- Steam 自带 GTK2 2.24.10 在 `XRRGetOutputInfo` 返回 NULL 时崩溃；2.24.33
  上游仍缺少这处检查。`scripts/personal/steam/` 提供 Niri 专用的启动兼容层，
  仅 Steam 主进程中 GTK2 的失败 RandR 查询得到“输出已断开/CRTC 已停用”的空记录。
  正常查询结果和其他调用者不变；构造函数恢复原 LD_PRELOAD，子进程/游戏不继承此库。
  不覆盖系统库、Steam runtime 或驱动；Hyprland 直接执行原 `/usr/bin/steam`。
- 部署 live 后执行 `python3 ~/.config/quickshell/inir/scripts/personal/steam/install.py`
  编译 32 位库至 `~/.local/share/inir/steam/`，安装 `~/.local/bin/steam` 和同 ID 的
  `~/.local/share/applications/steam.desktop`。需要 gcc、32 位 libc 和 Xrandr 头文件。
  安装器备份既有受管文件，遇到未知自定义 Steam 入口则拒绝覆盖。Steam 更新不覆盖此层；
  overlay 更新兼容层源码后重新运行安装器编译即可。
- 回退 Steam 修复：删除以上新增的受管桌面入口、启动器及 `inir/steam/` 目录（已有文件
  可从 `~/.local/state/inir/backups/steam-randr-*` 恢复），系统 Steam 文件始终保留。
  直接使用 `/usr/bin/steam` 可绕过兼容层。

## 验收

### 本机显卡、光标、启动项与个人键位（2026-10-06）

本机内屏 eDP-2 接 AMD Cezanne，HDMI-A-1 接 NVIDIA RTX 3060 Laptop。
两张卡驱动均已加载；NVIDIA 615.71.09 的 DRM modeset 已开启，Niri 为 26.04。
独立的 `config.d/05-personal-gpu.kdl` 按
[Niri 官方 render-drm-device 文档](https://niri-wm.github.io/niri/Configuration%3A-Debug-Options.html#render-drm-device)
指定 NVIDIA 为主渲染卡，使用稳定的 PCI render-node 路径；AMD 继续参与内屏输出。
Wayland 应用可通过 Niri 的 DMA-BUF 反馈选择主卡；Niri 启动的 GLX/XWayland、Vulkan
应用另有 NVIDIA PRIME 偏好。不复制 `AQ_DRM_DEVICES`、`WLR_*`，不设置全局驱动环境文件。
`INIR_SHELL_GPU_PREFERENCE=compositor` 让 iNiR 跟随 Niri 的 GPU 选择，本机为 NVIDIA，
与 `resources.monitorGpu` 开关无关。2026-10-06 的运行对照中，停止 AMD 渲染的 iNiR 后
用户确认鼠标明显流畅；将同一套 shell 改为 NVIDIA 后仍然流畅，恢复 AMD 后迟缓复现。
因此不再把 Hyprland 下 II 的核显策略直接用于 Niri。Hyprland 的 II 设置保持独立。
`integrated` 选项仍可显式启用；该模式启动普通应用时恢复覆盖前的应用 GPU 变量。
会话发布器和 iNiR 启动器清除空的 GPU 选择变量，避免 D-Bus 留下的
`__EGL_VENDOR_LIBRARY_FILENAMES=` 禁用 EGL 驱动。空的 FFmpeg 硬解列表仍保留其软件解码含义。

本次鼠标改善的证据来自 shell GPU 对照。单独的 NVIDIA GEM 内存错误补丁已加载，
但不能将鼠标改善归因于它；完整 Niri → Hyprland → Niri 切换仍需验证。

内屏 125% 缩放需要 Qt 的 `QT_SCALE_FACTOR_ROUNDING_POLICY=PassThrough`。
此前强制 `RoundPreferFloor` 会关闭 Qt Wayland 的分数缩放协议，退回 200% 缓冲区：
2048×1280 逻辑尺寸绘制为 4096×2560，再缩小到 2560×1600，增加绘制与跨显卡复制量。
启动器和服务统一采用 PassThrough，保留 `QT_SCALE_FACTOR=1` 及 QML 自身的界面缩放。
Vulkan、实际时间动画驱动和暂停壁纸的对照未消除内屏迟缓，均未作为持久设置保留。
只影响 Niri/iNiR，不改变 Hyprland、II、鼠标样式或共享壁纸服务。
主 GPU 在 Niri 启动时确定，热重载不能切换；同步后需退出 Niri 再从 GDM 登录，
并重启旧应用。重登后的应用选卡、多屏渲染、休眠唤醒及流畅度仍需实际验收。
若实际观察到 Niri 的 NVIDIA 显存异常增长，再按
[Niri 官方 NVIDIA 文档](https://niri-wm.github.io/niri/Nvidia.html)
为 `niri` 进程设置 `GLVidHeapReuseRatio=0`；本次未全局添加驱动补丁。

Niri 光标和启动应用的 `XCURSOR_THEME/SIZE` 使用现有的黑色
`Bibata-Modern-Classic`、24 像素。没有修改共享 GTK/GSettings、Hyprland 或 Kitty 设置。
输入法使用 Wayland text-input，XWayland 保留 `XMODIFIERS=@im=fcitx`。

Fcitx5、1Password 已在现有 XDG autostart 中，由 Niri/systemd 启动，避免重复添加。
CC Switch 不随 Niri 登录自动启动，按需手动打开。
KGpg、KDE 日历提醒（kalendarac）和 KDE 时钟后台（kclockd）的用户级 XDG 启动项
设为 `Hidden=true`，两种桌面都保留手动打开和原有数据。KGpg 是密钥管理界面，
关闭它的自启动不影响 gpg/gpg-agent；其 KDE 专用启动条件在 Niri 下会直接放行，
因此使用标准 XDG 覆盖而不依赖该条件。II 的日历使用 khal/ICS，便签、闹钟和提醒
使用自己的数据与定时器，不依赖 Akonadi/KNotes/kclockd；手机功能使用的 KDE Connect 保留。
残留 ToDesk 用户启动项增加 `TryExec=/opt/todesk/bin/ToDesk`，程序不存在时跳过，
重新安装到原路径后仍可自启动。上述策略由 `scripts/personal/configure-autostart.py`
维护，安装器先备份原启动项。不卸载旧 KDE 包、不改 Akonadi 数据或系统库。
自定义启动文件中已注释的 Clash Verge、HyprGlass、插件加载命令不迁移；
原有其他 XDG 应用仍按各自启动项运行。
用户已明确不再需要 libinput-gestures：本机的 XDG 项设为 `Hidden=true`，
用户服务已禁用并停止，保留程序和配置以便恢复。没有添加 Niri 特例或更改 Hyprland 原生手势。

Niri 下跳过系统的 Xwayland Video Bridge XDG 自启动项，避免捕获辅助窗口进入平铺布局。
通过生成服务的 `20-inir-session.conf` drop-in 检查桌面环境实现，不修改系统 desktop 文件，
其他桌面仍沿用原启动行为。已有的 `xwayland-satellite` 和 Niri 屏幕共享 portal 不受影响。
启用鼠标悬停聚焦，鼠标进入部分可见窗口时也允许对应列滚动到视野内。
个人触摸板配置 `95-personal-input.kdl` 保留自然滚动，同时显式启用轻点和
`left-right-middle` 按钮映射，避免覆盖上游触摸板段时丢失轻点设置。

个人键位独立放在 `defaults/niri/config.d/75-personal-binds.kdl`，上游 `70-binds.kdl` 保持原样。
个人文件沿用上游的分节注释，并用 Niri 原生 `hotkey-overlay-title="说明"` 定义显示名称。
设置页和快捷键速查表共用动作分类逻辑；分节注释只供阅读，不是分类指令。
原生标题优先显示，分类根据实际动作确定，因此中文或自定义标题不会使分类失效。
已识别的名称和分类会随界面语言翻译；`Other` 仅表示暂未识别的动作，不表示个人快捷键。
主配置先加载 70，再加载 75，最后加载用户自留的 90。Niri 26.04 的后续同键定义会替换旧动作，
等效于先解除旧绑定再重绑，不会同时触发两个动作；它不支持 Hyprland 的独立 `unbind` 指令。
多步操作由
`scripts/personal/niri-actions.py` 使用 Niri IPC 完成，不调用 Hyprland 脚本。

| 快捷键 | Niri 行为 |
|---|---|
| Ctrl+Alt+= / -；Ctrl+Shift+滚轮上 / 下 | 通过本机安装的 `~/.local/bin/niri-zoomctl` 放大 / 缩小屏幕；登录时启动 `niri-zoomd`；快捷键在设置页和速查表归入 System |
| Ctrl+Alt+Z | 重置屏幕放大镜；保留 Ctrl+滚轮的应用缩放、Super+Ctrl+滚轮的工作区移动、Ctrl+Alt+滚轮的音量操作 |
| Super+Enter / Super+T | 打开配置的终端（默认 Kitty）；个人环境补齐 `~/.local/bin`，保证 Niri 能找到 `inir` 启动器 |
| Super+Q / Alt+Q | 共用个人关闭动作，与 Nyxuri 一致：普通窗口直接关闭；仅 Folia 主窗口隐藏到自身托盘并继续播放，托盘不可用时不退出；Folia Remote 等其他窗口正常关闭 |
| Ctrl+Shift+Esc | 在 Kitty 中打开 btop 系统监控 |
| Alt+H/J/K/L | 左右聚焦列，上下聚焦列内窗口 |
| Super+H/J/K/L | 左右移动列，上下移动列内窗口 |
| Super+Shift+H/J/K/L；Super+-/= | 调整窗口宽高，每次 30 像素 |
| Super+N/P | 下一个/上一个工作区 |
| Super+Alt+N/P、H/L、方向键、滚轮 | 移动窗口到相邻工作区并跟随 |
| Super+Ctrl+Shift+H/L | 移动到相邻工作区，不跟随 |
| Super+Ctrl+Shift+N/O | 移动到/聚焦当前显示器末尾的空工作区 |
| Super+W | 浮动并设为 50%×60%、居中；再次按恢复平铺 |
| Super+O；Super+Shift+F；Super+Shift+O | 最大化列；全屏窗口；窗口伪全屏 |
| Super+F/E/I | 浏览器；Dolphin 优先的文件管理器；iNiR 设置 |
| Super+Space/Tab；Alt+Space | Niri 概览；iNiR 启动器（随面板家族路由） |
| Super+A/B；Super+Shift+Alt+J/K | 左/右侧栏；状态栏/屏幕键盘 |
| Super+Backspace；Super+Shift+Backspace | 锁屏；休眠 |
| Ctrl+Alt+P/H/L/M、方向键、J/K、滚轮、前后侧键 | 播放暂停、切歌、静音、音量 |
| Ctrl+1、Ctrl+Alt+左键；Ctrl+Alt+S/A/右键 | 区域截图；iNiR 截图工具菜单 |
| Ctrl+Shift+A/Z/Space | Kitty+tmux；1Password 主窗口/快速访问 |
| Super+Alt+F、Ctrl+Super+F | 重启 Fcitx5 |
| Super+Ctrl+W；Super+Alt+I/E；Super+Shift+E | skwd-wall-v2；GNOME 设置/XWayland 文件管理器；Rofi 文件浏览 |
| Ctrl+Super+/；Ctrl+Super+Alt+/ | 编辑 iNiR 设置；编辑 Niri 键位文件 |
| Super+Ctrl+Alt+Escape | 带确认的退出 Niri（释放 Super+Shift+E 给 Rofi） |

Niri 是滚动平铺：左右移动默认操作列，不保证与 Hyprland 的任意窗口换位相同。
Hyprland 的工作区组 ±10、任意 clean submap、额外鼠标键 6/7、
笔记专用开关、五指自定义手势和单独松开 Super 没有在本次中伪造等价行为。
仍保留 Niri 的 Super+鼠标左/右键移动/缩放手势和原有专用列操作。
截图编辑使用 iNiR 自己的工具；没有执行包含 `hyprshot` 的旧脚本。
Super+Shift+O 已解除上游关闭显示器动作，改为窗口伪全屏。
设置 UI 读取合并后的键位，新增/编辑写入 75 个人文件；删除使用显式无操作绑定，
防止简单注释后意外恢复上游动作。90 文件仍保留最高优先级的手工覆盖。

已提供临时目录隔离测试和离屏 QML 后端测试：

```sh
python3 scripts/test-personal-overlay.py
python3 scripts/test-shared-data-boundaries.py
python3 scripts/test-shared-app-colors.py
python3 scripts/test-skwd-backend.py
python3 scripts/test-disabled-wallpaper-backends.py
python3 scripts/test-wallpaper-authority.py
python3 scripts/test-runtime-payload.py
python3 scripts/test-safety-boundaries.py
niri validate --config defaults/niri/config.kdl
```

已完成：27 项个人隔离测试、8 项共享数据/样式/服务离屏测试、11 项共享应用配色测试、Go 编辑器配置保护测试、10 项分发测试、完整本地分发检查、Niri 校验及修改文件的 QML/Shell 语法检查。本次本地分发检查因尚无 iNiR Python 环境跳过终端配色数值测试；上一轮已用临时目录内的 v3.0.4 库通过该项，未修改 II 的 Python 环境。

需要部署后实际确认：

- GDM 选择 Niri，Shell 正常出现，日志无 QML 加载错误。
- skwd 显示静态/视频壁纸；在 skwd 外部切换后 iNiR 预览跟随。
- 壁纸配色生成一次，共享应用颜色更新。
- 从 Niri 注销再进入 Hyprland，II 的配置、待办、通知和终端基础设置保留。
- 返回 Hyprland 时 skwd 重新连接，壁纸和配色监听工作正常。

配色依赖固定为 `materialyoucolor>=3.0.4,<4`：新版 prerelease 需要 v3 的 ARGB 返回接口，II 的 v2 环境保持原样。

本轮只修改仓库源码；实际登录、渲染性能及会话切换未验收。

## 2026-10-05 复审修复

先前改动尚有遗漏，本次已补齐：

- awww 禁用时不探测、不预览、不执行 `awww kill`；web 后端禁用时也不创建会执行清理命令的输出实例。
- Waffle 禁止旧着色器壁纸叠加到 skwd 上；主背景和 Waffle 的缩略图、设置页的显示器预览跟随活动壁纸。
- AI、截图、剪贴板、识曲、语音搜索、Cava 临时配置采用统一私有运行目录；音乐播放器的 socket 与遗留进程清理只针对 iNiR。
- 更新备份及保留数量清理改到私有状态目录，支持 `INIR_STATE_DIR`；退役的 Python 迁移脚本即使单独调用也不修改共享 Shell 配置。
- “Regenerate” 明确使用 `--noswitch --image`，只生成配色；移除没有调用者的 mpvpaper 强杀函数。
- 隐藏/禁用旧桌面渲染器的过渡、缩放和部分播放控件，设置页提供 skwd 原生控制入口。概览、锁屏和预览仍由 Shell 绘制，不属于第二个桌面壁纸后端。

旧后端源码仍保留用于减少上游合并冲突，但在本 overlay 的启动和切换路径中不运行。可选的 SDDM 安装工具与跨发行版依赖脚本仍保留在仓库；个人安装包装器不调用它们，不应把直接执行这些额外工具视为隔离安装流程的一部分。
复审覆盖正常安装、更新、卸载和 Shell 运行路径；主题、应用配色、skwd 状态及标准桌面服务按设计共享，因此不承诺同一用户同时运行两套图形会话时完全隔离。

## 最终安装审计补充

- 剪贴板通过 `scripts/cliphist-inir.sh` 使用与 II 相同的默认 cliphist 配置和数据库。解码图片等临时文件仍在 iNiR 私有运行目录。
- Shell 退出只清理 `inir.service` cgroup 内的缩略图进程，不清理共享 Quickshell 的运行索引。
- 安装预检检查必需命令、GDM/Niri 登录入口、Niri/skwd/共享配色的用户服务；拒绝把私有目录指向 II 的配置/状态树。
- GDM 不需要提前把 `~/.local/bin` 加入 PATH；包装器部署明确的启动器路径与 Niri/systemd 环境。备份包含服务 drop-in 和旧启动器。
- 隔离回归覆盖真实 cliphist 的共享读写与清空行为、Niri 环境生成及幂等性、缩略图清理归属，以及先备份后部署。测试使用临时配置，不等同于真实登录验收。

官方形式的 `./setup install`、`./setup install -y`、`./setup reinstall` 与 TUI 安装/重装已接入个人安装流程；原 `scripts/personal/install.sh` 保留为内部实现和兼容入口。仅入口统一，依赖复用、配置隔离、备份和 GDM 保护仍然生效。当前改动未推送到远端，重新 clone 上游不会得到这套行为。


## 共享格式与 Shell 样式复审

- 待办因字段和同步方式不同保持独立；通知历史、cliphist 与通用钥匙环使用 II 的兼容原生格式。
- 通知采用原子写入，读取失败不清空共享历史；钥匙环错误不初始化为空，并串行保存连续修改。
- 共享配色不能覆盖 Shell 透明样式；自定义 widget 路径遵守 `INIR_CONFIG_DIR`。
- CLI 重装和 TUI 安装入口统一经过个人预检与备份；旧 II Super 服务清理已停用，更新默认保留已有 Vesktop 主题文件。
- 离屏测试使用临时 XDG 目录、独立 D-Bus 和模拟钥匙环，不读取实际通知、任务和凭据。


## Kitty 复审

Niri/iNiR 默认启动同一个 `kitty`，沿用现有 `~/.config/kitty/kitty.conf`，不安装上游的 Kitty 基础配置。目前主机配置为 FiraCode Nerd Font、zsh、现有搜索/复制/缩放快捷键，以及 `remember_window_size no`。实际配置与 chezmoi 源文件逐字一致，Kitty 自身解析器检查为零错误。

两边现在写入同一个 `~/.local/state/quickshell/user/generated/terminal/kitty-theme.conf`；iNiR 不追加 include、不替换 `current-theme.conf` 链接、不创建另一份 `~/.config/kitty/theme.conf`。保留 II 提示符使用的扩展颜色槽。现有 globinclude 和指向共享文件的链接能读取任一会话产生的新配色；通过 SIGUSR1 通知 Kitty 重载。非默认 XDG 状态目录同样生效。

当前主机已有正确的共享颜色引用，无需修改 live Kitty 配置；配色生成与链接保留测试均在临时目录运行。自定义 Kitty 配置若没有引用这个共享文件，将保留自己的主题而不会被强制接入。

## 共享应用配置写入复审

默认配色刷新更新已有的颜色输出，保留应用基础设置：

- GTK 只合并命名颜色和颜色变量，保留 CSS 的导入、选择器、字体、尺寸、注释和现有符号链接；Matugen 的 GTK 模板先写生成目录，避免在合并前覆盖用户样式。遗留模板也经过同样的重定向，尊重 XDG 路径。
- KDE/Qt 只合并调色板字段，保留字体、图标、控件样式和其他分组。GTK `settings.ini` 不因配色刷新而重写。GTK 与 Qt 的关闭开关分别生效。
- Alacritty、Foot、WezTerm、Ghostty、btop、lazygit、Yazi 等继续生成颜色文件，保留原有配置和主题选择；已引用生成文件的应用会使用新颜色。Starship 只更新已经选中的 `ii` 调色板，保留提示符布局和自定义颜色项。
- Chrome 只更新可写的现有策略目录中的 `BrowserThemeColor`，保留其他策略及个人 Preferences；不再改变后台运行策略，也不为普通配色刷新请求提权或放宽目录权限。损坏的策略文件保持原样。
- VS Code 的 Python 和 Go 两种生成器都保留已有设置、自定义颜色和主题选择。Pear Desktop 更新生成 CSS；已有接入可继续使用，不自动添加主题或开启调试端口。

尚未引用生成配色的应用保留原主题；此分支不强制所有应用接入。上游的自动配置功能需要显式 `INIR_INSTALL_SHARED_APP_CONFIGS=true`；个人安装包装器固定关闭这个选项。可选接入后使用共享应用路径，影响两边会话，不属于 Shell 私有样式。

图标服务启动时读取共享的系统选择，不恢复私有配置中的旧值；用户在界面主动选择系统图标主题时仍会更新共享设置。网络和 USB 监控由各自的 Quickshell Process 管理，不再全局清理同名进程。Niri 夜灯只查询、停止 `inir-wlsunset.service`，随 `niri.service` 退出；不影响其他来源的 wlsunset。

SDDM 配色模块和模板后置钩子都要求实际登录管理器为 SDDM；GDM 主机上的遗留 SDDM 文件不会触发它们。安装的通用备份已确认只复制文件，不移动现有应用配置。

上述验证使用合成配置和模拟系统命令。本轮未安装、未修改实际应用配置、未推送；实际 GDM 登录仍需部署后验收。

## 维护和小组件安全复审

- 小组件创建、扫描和删除改用参数数组调用 Python，不再把名称或路径拼进 Shell 命令。拒绝越界名称、组件目录符号链接和逃逸的入口文件；创建不会覆盖已有组件。组件 QML 本身仍是可执行代码，只应加载可信来源。
- 安装、更新、回退、卸载和启动入口检查私有路径，拒绝与 II、常见共享应用目录及宽泛根目录重叠；维护入口还拒绝运行代码目录中指向外部的符号链接。该检查防止错误配置，不是对任意自定义路径或同用户恶意进程的沙箱。
- 文件复制拒绝目标符号链接；更新和卸载备份失败会中止后续替换或删除。新增备份目录限制访问权限，卸载备份使用独立临时目录；共享的 `sync-pixel-sddm.py` 不再列入卸载删除清单。
- 退出安装器不再删除固定的 `/tmp/buildyay`、`/tmp/buildparu`；可选 AUR 助手只清理本次创建的临时目录，失败向上传递。移除全权限免密码 sudo 的建议。个人安装流程仍跳过系统依赖安装。
- Chrome 配色脚本即使显式开启共享应用接入，也不创建系统策略目录、不提权、不放宽权限，只使用已有可写目录。

新增 11 项临时目录安全回归，已接入完整本地分发检查；覆盖恶意名称、路径别名、目标链接、备份失败、卸载保护、临时目录清理和浏览器权限边界。测试不读取真实凭据或通知数据。

## 安装回退边界补充

个人安装流程不会写入 `~/.config/hypr`、`~/.config/quickshell/ii` 或 `~/.config/illogical-impulse`，不会升级系统 Quickshell，也不更改共享 Shell 启动文件和默认应用。共享壁纸、配色在运行两套桌面时仍按前述设计联动；安装阶段不重新生成或应用共享配色。

最后一轮复审停用了会安装系统包的旧 Qt/浏览器迁移；Steam 迁移只转换 iNiR 的私有字段，不改 Millennium 主题。个人安装也跳过 YAMIS、壁纸附加资源和共享 Deno 下载；缺少兼容 Deno 时提示，YouTube 音乐的相关功能需单独补齐依赖。

安装前备份位于 `~/.local/state/inir/install-backups/<时间>-<进程号>/`（自定义状态目录时随之改变）。除已有 Niri、iNiR 设置、运行代码、私有用户状态和启动器外，备份包含各用户服务 target 下原有的 `inir.service` 链接，以及 `data/` 下旧的 iNiR 桌面入口和图标。只恢复这些明确对应的文件；不要整体覆盖共享 systemd 目录。该快照不包含系统包、整个 Python 环境或登录后的共享历史修改，卸载也不等于自动完整回退。

安全回归增加至 15 项，包括真实资源安装段的临时目录执行，以及系统包迁移、Deno 和 Steam 保护；个人安装测试同时验证新增备份内容。本轮仅修改仓库，未部署到实际桌面。

## 依赖检查补充

依赖需要补齐，保护配置不意味着不需要系统包。`python3 scripts/personal/dependencies.py` 输出必需缺项和可选功能缺项；`./setup install --check` 和正式安装都调用它，缺少必需项会在部署前中止。检查只查询命令和本地 `pacman -T`，保留当前提供 Quickshell 的 `quickshell-git`，不调用会卸载其他 Shell、替换 Quickshell 或全系统升级的上游依赖流程。

2026-10-05 本机核验：`plasma-integration`、`plasma-browser-integration`、Deno 2.9.7、主要 Qt/QML 和 Python 原生构建依赖已存在。必需缺项是用于 Shell 锁屏失败时兜底的 `swaylock`：

```sh
sudo pacman -S --needed swaylock
./setup install --check
./setup install
```

可选缺项包括 `mission-center`（默认任务管理器）、`lsp-plugins-lv2`（EasyEffects 均衡器）、`mpv-mpris`、`ttf-oxanium` 及部分 OCR 语言模型。英语和简体中文 OCR 模型已安装。按需要单独补齐，安装器会明确列出，不把可选功能缺项当成 Shell 无法启动。

系统包安装会作用于两边桌面，先查看包管理器事务；配置隔离不保证系统包永远不变。iNiR 的 Python 依赖仍由安装器装入私有环境。增加了依赖分类与替代 provider 回归，安全回归共 16 项；本轮没有执行系统包安装。

## 已安装后的壁纸状态复审

桌面静态图、视频和 GIF 的应用请求统一交给 `skwd-helm apply`。设置页取色、每屏预览、概览、Waffle 任务视图、欢迎页和随机壁纸目录统一读取 `skwd-helm current --json` 的活动输出；外部壁纸切换通过 watch 更新，不依赖 iNiR 保存的旧路径。多屏预览按屏幕选择，通用取色使用当前聚焦屏幕。

旧 Material/Waffle 的持久 backdrop 窗口在 skwd 模式下不创建，避免旧开关启用第二层桌面壁纸；桌面取色也不采用单独 backdrop 路径。锁屏、概览缩略图和选择器预览仍是 Shell UI，可从 skwd 视频生成静态预览，不是第二个桌面渲染后端。显式“仅从此图片取色”仍遵从用户选择，默认重新取色则查询 skwd；查询失败保留现有颜色。

离屏回归覆盖静态图、视频、GIF、外部切换、多屏聚焦切换、断连保留最近状态及 CLI 查询失败。测试用模拟客户端，不实际切换桌面壁纸。本机只读状态确认两块连接的输出由 skwd 播放视频；真实 Niri 会话切换后的可视验收仍待完成。

## 当前会话独占 Kitty 配色

iNiR 的 skwd-session 使用 `start niri --no-ii-theme`，先停止 II 的壁纸配色监听，再交接 skwd。iNiR 自行生成共享 `kitty-theme.conf`，避免 II 在取色后覆盖。Hyprland 启动仍恢复 II 监听；skwd 的壁纸管理和用户服务启用链接保持不变。重复激活当前会话也会停止错误启动的 II 监听。

## 壁纸应用配色与 NyxMellow 输入法

ThemeService 的签名与 debounce 包含 skwd 活动壁纸，外部选择器和 iNiR 选择器均触发 `--noswitch` 取色。手动主题与独立设置窗口不自动取色。个人偏好 `defaults/personal-app-theming.json` 将 iRiS 的 `materialForApps`、`accentForApps` 关闭，Kitty 等应用跟随壁纸，而不是固定的黑色表面与蓝色强调色。只影响应用配色，不改 iRiS 外观。个人安装应用该文件；用户配置中的其他字段保留。

NyxMellow 的三个模板来自 Nyxuri，加入私有 matugen/templates.json，由 iNiR 当前壁纸色板渲染。应用阶段只调用 Fcitx Classic UI 的 `ReloadAddonConfig`，不会重启输入法，也不修改输入法方案、字体或候选数量。共享主题已设为 nyxmellow；II 会话用自己的 Matugen 模板生成同名主题，按顺序登录时由当前桌面取色。

Washi 在部署的运行目录中使用 `go build -buildvcs=false`，避免缺少 Git 元数据时编译失败并永久沿用旧缓存。
