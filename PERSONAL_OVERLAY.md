# night/personal-overlay

本分支基于 `origin/prerelease` 的 `db2233ce`，用于 Night 的 Hyprland + II / Niri + iNiR 双会话。
本分支包含私有配置、共享 skwd-wall 与 GDM 安装适配；本轮尚未安装或推送。

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
Niri 启动脚本导入本会话的 Wayland 环境并重启 skwd-walld，使其重新连接当前合成器；再启动 II 的现有配色监听服务。
两套图形会话应依次切换，共享守护进程不提供同时登录两套桌面的隔离。

## GDM 与安装

保留 `/etc/systemd/system/display-manager.service -> gdm.service`。
直接使用已经安装的 `/usr/share/wayland-sessions/niri.desktop`，其中 `Exec=niri-session`。
GDM 登录时选择 **Niri**。标准入口通过 `niri.service` 启动；`inir.service` 仅挂在它的 wants 下，不随 Hyprland 启动。
不需要新增登录条目。`.deskto` 后缀的旧自定义条目通常不会被 GDM 识别。

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

## 验收

### 本机显卡、光标、启动项与个人键位（2026-10-06）

本机内屏 eDP-2 接 AMD Cezanne，HDMI-A-1 接 NVIDIA RTX 3060 Laptop。
两张卡驱动均已加载；NVIDIA 615.71.09 的 DRM modeset 已开启，Niri 为 26.04。
保留 Niri 自动选卡和多 GPU 输出支持，不复制 `AQ_DRM_DEVICES`、`WLR_*`，
也不全局设置 `__NV_PRIME_RENDER_OFFLOAD`、`__GLX_VENDOR_LIBRARY_NAME` 或 `LIBVA_DRIVER_NAME=nvidia`。
需要独显的单个程序可使用现有 `prime-run <程序>`；不改变其他桌面的驱动设置。
当前尚未实测 GDM 登录后的多屏渲染、休眠唤醒和独显 offload。
若实际观察到 Niri 的 NVIDIA 显存异常增长，再按
[Niri 官方 NVIDIA 文档](https://niri-wm.github.io/niri/Nvidia.html)
为 `niri` 进程设置 `GLVidHeapReuseRatio=0`；本次未全局添加驱动补丁。

Niri 光标和启动应用的 `XCURSOR_THEME/SIZE` 使用现有的黑色
`Bibata-Modern-Classic`、24 像素。没有修改共享 GTK/GSettings、Hyprland 或 Kitty 设置。
输入法使用 Wayland text-input，XWayland 保留 `XMODIFIERS=@im=fcitx`。

Fcitx5、1Password 已在现有 XDG autostart 中，由 Niri/systemd 启动，避免重复添加。
新增 CC Switch 登录启动，先有限等待托盘，并检查当前用户是否已有实例。
自定义启动文件中已注释的 Clash Verge、HyprGlass、插件加载命令不迁移；
原有其他 XDG 应用仍按各自启动项运行。
用户已明确不再需要 libinput-gestures：本机的 XDG 项设为 `Hidden=true`，
用户服务已禁用并停止，保留程序和配置以便恢复。没有添加 Niri 特例或更改 Hyprland 原生手势。

Niri 下跳过系统的 Xwayland Video Bridge XDG 自启动项，避免捕获辅助窗口进入平铺布局。
通过生成服务的 `20-inir-session.conf` drop-in 检查桌面环境实现，不修改系统 desktop 文件，
其他桌面仍沿用原启动行为。已有的 `xwayland-satellite` 和 Niri 屏幕共享 portal 不受影响。
启用鼠标悬停聚焦，鼠标进入部分可见窗口时也允许对应列滚动到视野内。

个人键位独立放在 `defaults/niri/config.d/75-personal-binds.kdl`，上游 `70-binds.kdl` 保持原样。
主配置先加载 70，再加载 75，最后加载用户自留的 90。Niri 26.04 的后续同键定义会替换旧动作，
等效于先解除旧绑定再重绑，不会同时触发两个动作；它不支持 Hyprland 的独立 `unbind` 指令。
多步操作由
`scripts/personal/niri-actions.py` 使用 Niri IPC 完成，不调用 Hyprland 脚本。

| 快捷键 | Niri 行为 |
|---|---|
| Super+Q | Niri 原生关闭窗口，不经过 Shell 关闭脚本 |
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
