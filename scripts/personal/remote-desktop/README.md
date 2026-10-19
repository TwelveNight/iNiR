# 所有桌面共享的远程桌面控制器

这一目录是 `~/.local/libexec/remote-panel` 的可版本管理来源。适配本机的
`inir`、`nyxuri`、`hyprland-ii` 三个登录配置；服务与认证信息仍全局共享。
部署不需要运行整个 iNiR 安装器：

```sh
python3 scripts/personal/remote-desktop/install.py
python3 scripts/personal/remote-desktop/install.py --apply
python3 -m unittest discover -s scripts/personal/remote-desktop -p 'test_*.py'
```

安装器先验证两个 Niri 配置并保存备份；拒绝在 VNC、Moonlight 或其准备服务
使用中安装。只重启布局控制器，保留已认证的 WayVNC 服务进程与 uinput 后端。
不改认证、证书、网络、编码器、码率或 Sunshine 的固定内屏捕获设置。

当前 compositor IPC 取自用户 systemd 的 JSON 环境；通过 Unix socket 的 peer PID
读取 compositor 本身的桌面身份，忽略 manager 残留的旧 `DESKTOP_PROFILE`，并与 `~/.config/niri` 或 `~/.config/hypr`
指向的已安装 profile 核对；操作前验证会话 IPC。不会按仍存在的旧 socket 或
进程启动时遗留的环境选择桌面。Niri 的合盖标记位于各 profile 自己的
`remote-panel__custom__.kdl`，由保留更新的个人入口加载。Hyprland 使用本机
Lua `hl.monitor` API，不写 Niri 文件。

同一 Niri 进程内的受控热切换使用
`$XDG_RUNTIME_DIR/desktop-profiles/niri-handoff.json`。控制器仅接受当前用户拥有、
其他用户不可写的普通文件，且其 `pid`、`started`（`/proc/PID/stat` 的启动时钟）、
`socket`、`origin_profile`、`profile`、`config` 必须全部与已验证的 IPC 进程及
实际配置目录一致。没有匹配记录时，仍拒绝进程身份与配置链接不一致的情况；
记录不能跨重启或用于 Hyprland。切换过程须迁移远程布局快照与断开锁屏义务，
不能把仍在线的客户端当作断开处理。

VNC 连接时保存完整的内外屏状态，将 eDP-2 放在 `(0,0)`，关闭其他输出，
只把 eDP-2 交给捕获服务。多客户端共用此状态，最后一个远程客户端离开后
先确认锁屏，再恢复此前的分辨率、缩放、旋转、位置与启停状态。外屏先恢复，
以免合盖时没有可用输出。快照与锁屏义务绑定 profile 和 compositor IPC；
换桌面或重新登录后不会把另一会话的布局写到当前桌面。

锁屏确认按实际桌面选择：iNiR 的 `lock status` 必须返回 `secure`；Nyxuri 用
当前 Noctalia 的 `locked=true`；Hyprland 调用 II 锁屏并查询 compositor 的
`hyprctl -j status`，要求 `locked=true`。锁屏失败保留远程布局并重试。
远程连接期间单独持有 logind 合盖处理抑制，断开后释放。
控制器与准备服务使用 `KillMode=mixed`，停止时只先通知主进程，避免清理期间
正在运行的 compositor/网络探测子进程被一并终止而导致错误退出。

Moonlight 沿用显式准备流程：

```sh
systemctl --user start moonlight-inner.service
cat "$XDG_RUNTIME_DIR/moonlight-inner.json"
```

等待 `ready` 再连接现有配对的 Desktop。准备服务与正常 VNC 控制器使用相同
桌面适配器；启动门禁同时校验当前会话、准备进程 PID、内屏 `(0,0)` 和其他
输出已关闭。Sunshine 仍使用 AMD VAAPI / KMS / eDP-2，不允许失败后捕获外屏。
最后断开后停止 Sunshine，再恢复桌面。不要单独重启 Sunshine 绕过准备服务。

本机 iNiR 的日常布局由 `../display-layout.py` 管理：HDMI `(-2560,0)`，eDP-2
`(0,0)`。远程布局快照会恢复这个排列，不会把 HDMI 移回右侧。

备份在 `~/.local/state/remote-panel/install-backups/`。回退时按备份的
`manifest.json` 恢复原文件、删除此次新建文件，执行 `systemctl --user daemon-reload`
并重启 `remote-panel.service`；应在没有远程客户端时进行。

自动回归覆盖三个桌面的识别、命令与锁屏路由、快照隔离、内外屏恢复、
多客户端断开规则、锁屏失败重试与 Sunshine 门禁。实际跨桌面登录、合盖、
平板触控和持续视频需在对应桌面与客户端验证；当前会话检查不能代替这些验收。

## 本次验证（2026-10-19）

39 项共享控制器测试与 2 项显示布局测试通过，两个 Niri profile 的完整配置
验证通过；本机 Hyprland Lua 配置验证通过。实际 iNiR 合盖会话完成一次
Sunshine 准备与停止循环：KMS/VAAPI 就绪、eDP-2 位于原点、外屏关闭，
捕获到 2560×1600 的真实画面，随后完整恢复测试前的输出状态。
公开 WayVNC 服务保持原 PID，无客户端被断开。

Nyxuri 和 Hyprland 的实际登录串流、平板显示/触控及断开锁屏尚未实测；
这些桌面的当前证据为配置验证和适配器回归测试。

随后完成一次远程 iNiR → Nyxuri 热切换：Niri 与 WayVNC 保持原 PID，现有
VNC 客户端保持连接，内屏分辨率、缩放、位置及其他输出启停状态保持一致。
已查看真实内屏画面确认 Noctalia 面板渲染，Nyxuri 剪贴板服务运行，控制器
确认 `desktop_profile=nyxuri`、内屏捕获和断开锁屏义务。热切换期间没有注销，
这不替代完整登录、客户端断开及重新连接的验收。新增身份记录回归后共 41 项通过。
