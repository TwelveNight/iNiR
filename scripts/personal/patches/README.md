# 本机 NVIDIA GEM 引用修复候选

适用源码：`/usr/src/nvidia-615.71.09/nvidia/nv-dma.c`，原文件 SHA256：
`0382ba885442f2ca457a661b0e33a847732bf81f9a71034674c8489e28ca2536`。

2026-10-06 12:05:50（返回 Niri 后）和 12:07:54（重启后）内核记录：
`KFENCE: use-after-free read in nv_dma_release_sgt`，触发进程均为 Niri。

本机源码先调用 `nv_dma_gem_object_put_unlocked(gem)`，之后访问
`gem->dev->driver->fops->owner`。最后一个引用释放后，GEM 对象可能已被销毁。
补丁在释放前缓存模块 owner，并保持原有的“先释放 GEM、后释放模块”顺序。

此补丁是本地候选，尚未由 NVIDIA 确认。安装器不会应用它、重编译 DKMS、
安装模块或重启系统。编译验证不代表驱动运行验证，也不证明鼠标延迟全部来自该错误。
不应对其他版本自动应用，不应在正在使用 NVIDIA 的图形会话中卸载驱动。

验证结果：在临时源码副本应用补丁，针对本机 `7.2.8-zen1-2-zen` 的完整模块编译
成功（make exit 0）；`nvidia.ko` 的 version 为 `615.71.09`，vermagic 对应该内核。
LTS `6.18.55-1-lts` 的完整模块编译也已成功，vermagic 对应该内核。
编译副本时系统源码原文件 SHA256 保持不变；运行验证需要安装后重新启动。

验证方式：复制本机整份 NVIDIA 源码到临时目录，在副本内执行
`patch --dry-run -p1 < nvidia-615.71.09-gem-owner.patch`，再应用并编译副本。
真实部署仍需要 root、DKMS/启动镜像检查和下一次启动后的会话往返测试。

显式部署入口（标准安装器不会调用）：

```sh
python3 scripts/personal/deploy-nvidia-gem-fix.py check
sudo python3 scripts/personal/deploy-nvidia-gem-fix.py install
```

部署脚本限定本机、源码校验值、驱动版本及两个已安装内核；备份原源码、
NVIDIA DKMS 状态、模块和四个启动镜像到 `/var/lib/inir/nvidia-gem-owner/backup-*`。
先完成两套 DKMS 编译再安装，失败自动恢复；不卸载已加载模块，不触发重启。
只重建内嵌 NVIDIA 模块的 initramfs；本机目前四个镜像都不内嵌该模块。
结果记录在 `/var/lib/inir/nvidia-gem-owner/status.json`。

回退命令：

```sh
sudo python3 scripts/personal/deploy-nvidia-gem-fix.py rollback --backup /var/lib/inir/nvidia-gem-owner/backup-实际编号
```

驱动更新到其他版本后，脚本会拒绝回退，以免混用模块和用户态库。包更新会覆盖
本补丁；应核对新源码是否已修复该问题，不自动把旧补丁套在新驱动上。

已完成的配置修复与本补丁独立：关闭 Docker Desktop/Sunshine 自动启动，
让 Niri/Hyprland 发布各自的 GPU/Wayland 环境，并在注销时释放共享壁纸的旧客户端。
