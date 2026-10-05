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

当前主机最后一次只读预检（2026-10-05，本次复审）已通过，包含 `swayidle`、GDM/Niri 入口和三个用户服务。安装前可再次检查：

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

已提供临时目录隔离测试和离屏 QML 后端测试：

```sh
python3 scripts/test-personal-overlay.py
python3 scripts/test-shared-data-boundaries.py
python3 scripts/test-skwd-backend.py
python3 scripts/test-disabled-wallpaper-backends.py
python3 scripts/test-runtime-payload.py
niri validate --config defaults/niri/config.kdl
```

已完成：24 项个人隔离测试、6 项共享数据/样式离屏测试、10 项分发测试、完整本地分发检查、Niri 校验及修改文件的 QML/Shell 语法检查。本次本地分发检查因尚无 iNiR Python 环境跳过终端配色数值测试；上一轮已用临时目录内的 v3.0.4 库通过该项，未修改 II 的 Python 环境。

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
