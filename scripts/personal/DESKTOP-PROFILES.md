# 登录时选择 Niri 配置

本机 iNiR 的配置实体是 `~/.config/desktop-profiles/inir/niri`。
GDM 的 Niri 项先执行 `desktop-profile run inir`，再运行标准 niri-session。
安装器与更新器在写文件前验证 `~/.config/niri` 属于 iNiR；另一个 Niri
桌面运行期间不会临时切换其配置。目录同步只在归属验证后解析受管理的 niri 链接，
仍拒绝其他任意目录软链接。

在 iNiR 中沿用 `inir update --local`。跨桌面维护可在 TTY 执行：

```sh
desktop-profile maintain inir -- ~/Template/github/niri-dots/iNiR/setup update --local
```

完整设计和回退方式见 `~/.local/lib/desktop-profiles/README.md`。

已有 profile 即使没有 iNiR 的首次安装标记，也保留整套 Niri 配置；安装器只
应用已有的启动器和主题兼容补丁，不运行会删除个人文件的 defaults 同步。
`remote-panel__custom__.kdl`、加载它的 `config.d/90-user-extra.kdl` 以及
HDMI 在左、eDP-2 位于原点的显示配置都随现有 profile 保留。

安装备份的 `config/niri/` 是配置实体的独立副本；原活动链接记录在同级
`niri-link`。回退时先在 TTY 选择 iNiR，将快照内容恢复到
`desktop-profile path inir niri` 返回的目录，保留 `~/.config/niri` 的管理链接；
不要用备份目录替换整个 `~/.config`。

隔离回归：`python3 scripts/test-personal-overlay.py`。

三套源码合并、验证、live 更新和冲突处理见 [DESKTOP-UPDATES.md](DESKTOP-UPDATES.md)。
