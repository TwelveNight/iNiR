# 个人桌面的更新

iNiR、II、Nyxuri 源码保留在 `night/personal-overlay`；Vitreus 两套共用
`personal-overlay`。部署目录与仓库分离。

| 桌面名 | 源码目录（`~/Template/github/` 下） | 合并来源 |
| --- | --- | --- |
| inir | niri-dots/iNiR | origin/prerelease |
| hyprland-ii | hyprland-dots/ii-p3drovfx | origin/dev |
| nyxuri | niri-dots/Nyxuri-personal | origin/main |
| vitreus / vitreus-wm | hyprland-dots/Vitreus | origin/main |

首次安装统一入口：`bash scripts/personal/install-desktop-update.sh`。
它读取 `~/.config/desktop-profiles/profiles.json` 的源码位置。

## 日常更新

```sh
desktop-update status all     # 离线查看已有远程引用
desktop-update check all      # fetch 官方上游，只检查、不合并或部署
desktop-update sync all       # fetch + merge，验证；不更新 live
desktop-update deploy all     # 再验证、备份、部署已合并的本地源码
```

也可合并执行：`desktop-update update all`。单套更新将 all 换为
inir、hyprland-ii、nyxuri、vitreus 或 vitreus-wm。Vitreus 两个名字操作
同一份源码和两套隔离部署，all 只更新一次。`--plan` 只展示路径和命令，不联网或写文件。
status 使用已有远程引用；check/sync/update 刷新官方上游，不把个人分支名当远端分支。
check 允许工作区有修改；--json 输出 profile、upstream、behind/ahead 和提交 SHA。
iNiR 的更新提示检查 origin/prerelease，II 通过统一入口检查 origin/dev；
个人提交不会被当成需要自动修复/reset 的上游历史分叉。

在当前桌面可用 `inir update`、`ii-p3drovfx update`、`nyxuri update`，
它们会进入相同的个人流程。显式 `--local` 只部署，避免再次拉取。
手动审查后的源码也可先 `desktop-update verify all` 再 deploy。

更新另一套 Niri 配置时，如果当前 Niri 正在使用不同的 profile，管理器
会拒绝切换其链接。此时注销图形会话，在 TTY 登录后执行 deploy/update。
sync 在任意桌面都能运行。工具不替用户注销或重启 compositor。
Hyprland 安装器仅在 Hyprland 运行时重启自己的 II；iNiR 更新可能重启
自己的 shell。Nyxuri 文件部署不重启 shell，新登录加载新配置。
远程捕获服务不由这个流程重启。
Vitreus 安装器要求退出 Vitreus/Vitreus WM 后部署；在其会话中可以 check/sync，
但 update/deploy 会在 live 写入前停止并提示注销。在其他桌面/TTY 可自动验证、备份、部署。

## 合并规则与冲突

工作树必须干净，分支、官方 origin 地址均需匹配。每次 merge 前保存
`refs/desktop-updates/时间` 回退引用。合并保留个人提交，不 reset/rebase，
不自动 stash 或 push。新上游仍可能产生语义冲突，不能保证永久免审查。

发生冲突会保留 Git 合并现场并停止，后续 live 部署不执行。终端和桌面通知
会要求在对应源码目录打开 AI 修复冲突并提交，然后重新 update：

```sh
cd 对应源码目录
git status
# 按功能解决冲突，保留 personal 层及 profile 路径
git add 已解决的文件
git commit
desktop-update update 桌面名
```

放弃尚未完成的合并可执行 `git merge --abort`。已经合并的历史用新的
revert 提交回退，不在个人分支上使用 reset --hard 或强制推送。

## live、chezmoi 和回退

部署前备份在 `~/.local/state/desktop-profiles/updates/时间-桌面名/`，
保留配置实体和相应 shell 的独立副本。各安装器也保留原有备份。
HDMI 左侧、eDP-2 原点、remote-panel 自定义和 Hyprland custom/ 继续保留。

chezmoi 管理 iNiR/Hyprland 的配置实体，Nyxuri 由个人安装器管理。
只针对安装器本次修改的已管理文件同步回 chezmoi；若源文件在更新前已经
与 live 不同，停止同步并人工审查，避免覆盖尚未部署的个人编辑。
不要全量 re-add 整个 ~/.config 或把运行时 shell 目录收进 chezmoi。

回退应在 TTY 完成：从备份恢复该 profile 的内容及对应 shell，保留
`~/.config/niri` / `hypr` 等标准链接，再运行 compositor 配置验证。
源码回退与 live 还原是两个动作；备份不会自动回退 Git，也不会自动删除。

个人修复按功能 commit；推送另行决定，例如在对应仓库执行
`git push personal night/personal-overlay`。统一更新工具不会推送。

## 定时检查

`bash scripts/personal/install-desktop-update.sh --enable-timer` 安装并启用
用户级 `desktop-update-check.timer`。每六小时（加最多十五分钟错峰）执行
`desktop-update check all --notify`，只 fetch/check，不合并或部署。
仅检查已注册的桌面；一套无法联网不会阻止检查其余桌面。同一上游提交
只通知一次，记录位于 `~/.local/state/desktop-profiles/update-notified.json`。
关闭：`systemctl --user disable --now desktop-update-check.timer`。
SekaiPop 保留自己的设置页检查及 `bash update.sh` 更新入口。
