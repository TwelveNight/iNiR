# 本机显示布局

HDMI-A-1 在左侧 `(-2560, 0)`，eDP-2 在右侧 `(0, 0)`。
将 HDMI 放在负坐标，可以保持远程捕获内屏的坐标原点，远程断开后也不必移动内屏。
分辨率、刷新率和缩放沿用原有设置。

本机 iNiR 的配置实体为 `~/.config/desktop-profiles/inir/niri`。
`monitor.kdl` 和 `config.kdl` 曾重复定义输出，且前者的旧位置优先生效；
修复同时更新这两处位置，避免只改主配置后布局仍然错误。

需要重新应用时运行：

```sh
python3 scripts/personal/display-layout.py --check
python3 scripts/personal/display-layout.py
```

脚本会先验证完整候选配置，备份原文件，再只改输出位置；不安装整个桌面，
不修改远程桌面服务，也不改其他桌面的显示器设置。
`--hdmi-width` 接收 HDMI 缩放后的逻辑宽度，本机目前为 2560。
