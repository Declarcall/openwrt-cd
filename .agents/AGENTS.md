# OpenWRT-CI Build & Dependency Rules

> **核心铁律**：**严苛遵守物理路由器原版 U-Boot 的物理规范（原厂 6MB 分区对齐与 GZIP 解压算法），绝对严禁编译原版 U-Boot 无法安装/无法开机的镜像**！严禁图省事阉割功能、删除依赖、绕过报错、篡改 KERNEL_SIZE 物理分区表或强行替换为 U-Boot 不支持的 LZMA 算法。编译固件的核心且唯一首要目标，是**确保生成的镜像能在真实物理路由器（雅典娜/亚瑟等）的原版 U-Boot 下 100% 成功刷入、物理分区对齐、顺畅引导开机且硬件加速全开**。
> **上游对齐铁律**：**遇到任何编译、内核配置、打包异常或行为疑问时，必须且唯一以标杆仓库 [VIKINGYFY/OpenWRT-CI](https://github.com/VIKINGYFY/OpenWRT-CI) 为权威基准进行代码与配置比对，绝对严禁任何未经权威基准验证的主观臆断、盲目修改或乱加 sed 补丁**。
> **强制前置规则**：在执行任何 CI 编译任务、修改配置文件、编写 Shell 脚本或调试报错前，必须先复核并严苛遵循项目标准构建链路文档 [openwrt_standard_build_flow.md](file:///.docs/openwrt_standard_build_flow.md)。

## 1. 编译期磁盘防爆原则 (Build-Time Disk Space Guard)
- ** Runner 极限空间清理**：每次 CI 编译前必须清理 GitHub Actions 预装的无用软件（含 `.NET`, `Android SDK`, `GHC`, `CodeQL`, `Powershell`, `Swift`, `Chromium`, `Boost`, `JVM`, `Docker/Containerd cache`, `Pipx`, `Vcpkg`, `Node_modules`），确保虚拟机保持 60GB+ 可用空闲。
- **避免重型 GUI/C++ 依赖**：严禁在默认配置中引入 `Qt6` (`qt6base`, `qt6tools`), `rblibtorrent` 等巨型 C++ 框架。
- **Golang 模块代理加速**：始终在构建阶段配置 `export GOPROXY=https://proxy.golang.org,direct`。

## 2. 严格依赖与变体审计原则 (Strict Dependency & Variant Audit)
- **eBPF (大鹅 dae) 编译绝对基准铁律**：**凡是涉及到编译大鹅 `dae`，必须且唯一以标杆仓库 [davidtall/DaeWRT-CI](https://github.com/davidtall/DaeWRT-CI) 为第一权威基准**！必须使用 `package/dae` 根目录下移除了 `vmlinux-btf` 依赖规则的极简 Makefile 架构，在 `Packages.sh` 中执行 `rm -rf ./luci-app-dae/dae` 并清理 `feeds` 中原生的 `dae*` 重名包，且必须安装 Host 端 `clang`, `llvm`, `lld` 工具链并引入 `v2ray-geodata` 规则库。
- **变体裁切与避坑规则**：对于存在废弃依赖的包变体（如 `avahi` 的 `dbus` 变体依赖缺失的 `libdaemon`），必须显式禁用该变体 (`avahi-dbus-daemon=n`) 并启用稳定变体 (`avahi-nodbus-daemon=y`, `umdns=y`)。
- **同名包碰撞预防**：开启 `dnsmasq-full=y` 时，必须显式禁用基础版 `dnsmasq=n`。
- **第三方仓库提取模式**：使用 `Packages.sh` 脚本提取多包仓库（如 `fw876/helloworld`）时，确保使用正确的解压模式（`"name"` 模式）。

## 3. 依赖图完整性原则 (Dependency Graph Integrity Rule)
- **优先补齐源码而非篡改依赖图**：遇到缺失依赖库时，必须通过 `Packages.sh` 克隆补齐该依赖包的源码，绝不能盲目用 `sed` 强行抹除 `Makefile` 中的 `DEPENDS:=+pkg` 依赖声明。抹除依赖声明会破坏 OpenWRT 的编译拓扑顺序（导致依赖库未先编译进 `staging_dir`，目标包提前编译报错）。
- **严禁虚构 Autoconf/Configure 参数**：严禁在 `Handles.sh` 中擅自注入未经上游 `configure.ac` 验证的构建参数（如不存在的 `--disable-libdaemon`）。遵循 OpenWRT 标准构建链路。

## 4. Alpine `apk-tools` 打包与解耦原则 (APK Packaging & Source Decoupling)
- **版本号格式与下载文件名解耦**：ImmortalWRT 主线使用 Alpine `apk` 打包。对于形如 `0.4.0rc1` 的 RC/Beta 包版本，`apk mkpkg` 必须要求下划线格式（`0.4.0_rc1`）。修补 `PKG_VERSION` 时，**必须同步显式指定 `PKG_SOURCE:=pkg-0.4.0rc1.zip`**，防止 OpenWRT 默认拼错 URL 导致源码包下载 404 失败。

## 5. 高通 NSS 硬件加速功能完整性原则 (Qualcomm NSS HW Acceleration Integrity)
- **严禁阉割加速功能规避报错**：遇到 `qca-nss-ecm` 提示 `nss_rmnet_rx_get_ifnum undefined` 等符号丢失报错时，**严禁通过关闭 `ECM_INTERFACE_RMNET_ENABLE=n` 阉割蜂窝加速**。必须在配置中补齐缺失的高通 NSS RmNet 驱动包（`CONFIG_PACKAGE_kmod-qca-nss-drv-rmnet=y` 与 `CONFIG_PACKAGE_kmod-qca-nss-clients-rmnet=y`），确保硬件加速 100% 全开且编译通过。

## 6. CI 诊断日志推送无损防卡原则 (CI Failure Log Push Reliability)
- **推送前工作区未暂存文件 Stash 隔离**：GitHub Actions 在编译失败推送日志前，必须先执行 `git stash -u 2>/dev/null || true`，清空 OpenWRT 编译过程产生的未暂存修改，确保 `git pull --rebase` 和 `git push origin dev` 100% 成功推送，绝不丢失日志。

## 7. 本地预检验证与线上 CI 加速原则 (Local Validation & CI Acceleration)
- **本地编译定位（快速预检）**：跑本地 Docker 编译的核心目的是**作为前置验证工具（Pre-flight Check）**。通过本地隔离环境预先跑通自动化脚本，提前拦截所有的依赖冲突、Makefile 语法错误及镜像体积超限，为线上编译避坑扫清障碍。
- **线上编译定位（高效产出）**：通过本地脚本 100% 验证无误后再推送，确保 GitHub Actions 线上 CI 能够一次性通关成功，避免在云端盲目试错等待，从而实现**极速、高效的线上云端固件构建与发布**！

## 8. 极速零消耗脚本监听原则 (Zero-Token Background Script Monitoring Rule)
- **脚本监听核心目的**：使用后台脚本监听任务的核心且唯一目的是**大幅节省 Token 消耗**。
- **严禁重复轮询唤醒**：在使用 Python 等后台脚本监听任务时，**严禁设置任何形式的周期性定时器（如 schedule）重复唤醒 Agent**。
- **OS 级完全静默**：后台脚本必须在操作系统底层完全静默运行（0 Token 消耗），只有当任务彻底完成或产生最终结果时，方可触发唯一一次通知，绝不产生无意义的上下文重送。

## 9. 硬件物理分区表对齐铁律 (Hardware Flash Partition Alignment Rule)
- **严禁篡改 `KERNEL_SIZE` 分区偏移**：`KERNEL_SIZE`（如 `6144k`）在 OpenWrt 的 `IMAGE/factory.bin := append-kernel | pad-to $(KERNEL_SIZE) | append-rootfs` 中，**决定了根文件系统 `rootfs` 的物理解包偏移地址**。改动 `KERNEL_SIZE` 会破坏路由器（如雅典娜/亚瑟等 eMMC 闪存设备）GPT 物理分区表对齐，导致 U-Boot 寻址 `rootfs` 失败而 Kernel Panic / 无 Wi-Fi / 无法开机。
- **依靠去除 DEBUG 符号进行 GZIP 瘦身**：遇到 `Build/check-size` 提示内核超限时，**必须保持原版 U-Boot 唯一支持的 `GZIP` 算法（`fit gzip` / `CONFIG_KERNEL_GZIP=y`）**，通过关闭臃肿的 `CONFIG_KERNEL_DEBUG_INFO` 与 `CONFIG_KERNEL_DEBUG_INFO_BTF` 将 GZIP 内核瘦身至 ~4.8MB（低于 6MB 分区上限 1.2MB），严禁替换为 U-Boot 不支持的 LZMA 算法，也严禁改大 `KERNEL_SIZE` 假通关。

## 10. Makefile 制表符与正则匹配安全原则 (Makefile Tab & Regex Safety Rule)
- **Makefile 必须兼容 TAB 缩进**：OpenWrt Makefile 语法规定 `define` 内部变量前使用 TAB 制表符 (`\t`) 缩进。在 Shell 脚本中使用 `sed` 修改 Makefile 时，**必须使用兼容 TAB 和空格的扩展正则表达式 (`sed -i -E 's/([[:space:]]*VAR[[:space:]]*:=).*/.../g')`**，严禁使用硬编码普通空格的 `sed` 导致匹配静默失效。

## 11. 高通 NSS / QCA-NSS-ECM 驱动完整性与 Safe Stub 补丁原则 (QCA NSS Acceleration & C Safe Stub Rule)
- **绝对保持 RAWIP 旁路加速全开**：遇到 `qca-nss-ecm` 的 `nss_rmnet_rx_get_ifnum` 符号未定义报错时，必须通过 `Handles.sh` 动态生成 `016-fix-rawip-rmnet-symbol.patch` 注入 C 语言层 Safe Stub 存根返回 `(-1)`，严禁直接关闭 `ECM_INTERFACE_RMNET_ENABLE` 导致移动 4G/5G 旁路加速功能丧失。详见 [qca_nss_ecm_compilation_guide.md](file:///.docs/qca_nss_ecm_compilation_guide.md)。

## 12. `Handles.sh` 脚本生命周期与 `.config` 修改时序原则 (Build Script Lifecycle Order Rule)
- **严禁在 `Handles.sh` 中对未初始化的 `.config` 写入**：`Handles.sh` 在 `Custom Packages` 阶段执行，而 `.config` 文件是在其后的 `Custom Settings` 阶段才被首次创建并执行 `make defconfig` 的。所有全局 `.config` 勾选必须直接写进 `Config/GENERAL.txt` 或在 `Settings.sh` 中写入。

## 13. 雅典娜 / 高通原厂 U-Boot 物理标准四项原则 (Athena Stock U-Boot Physical Standards Rule)
- **解压算法锁定 GZIP**：必须使用 `fit gzip` (`CONFIG_KERNEL_GZIP=y`)。原版 U-Boot bootm 引擎只支持 GZIP，严禁使用 LZMA/XZ。
- **分区大小锁定 6144k**：物理 GPT 分区表 `kernel` 大小为 6MB，`KERNEL_SIZE` 必须锁定为 `6144k`。
- **线刷首选 factory.bin**：U-Boot Web 恢复界面刷机必须使用 `factory.bin` 固件（同时刷新 kernel 和 rootfs 物理分区）。
- **内核体积瘦身至 4.8MB**：通过关闭 `CONFIG_KERNEL_DEBUG_INFO` 和 `CONFIG_KERNEL_DEBUG_INFO_BTF` 瘦身，使 GZIP FIT 镜像控制在 ~4.8MB（< 6MB 限制），实现秒级开机亮蓝灯。

## 14. 标杆仓库对照与实测验证方案双向保留原则 (Upstream Alignment & Verified Solution Preservation Rule)
- **逐行对照标杆仓库**：遇到任何编译失败、内核配置、打包格式或运行异常时，**必须第一时间逐行对照 [VIKINGYFY/OpenWRT-CI](https://github.com/VIKINGYFY/OpenWRT-CI) 标杆仓库**，彻底绝禁未经权威基准验证的主观臆断和瞎改。
- **保留已被实测验证正确的特化方案**：在与上游标杆仓库对比对齐的同时，**必须坚决保留本项目中已被实测证明 100% 正确的特化解决方案**（如原厂 U-Boot 6MB/GZIP 物理规范、NSS Safe Stub C 存根补丁、dae eBPF 工具链环境、apk-tools 404 解耦修补、Avahi nodbus 稳定变体），严禁盲目将已验证正确的特化修复当作“多余补丁”误删。

## 15. 本地仿真前置验证铁律 (Local Pre-Flight Simulation Rule)
- **修改前必须进行本地仿真测试**：遇到任何编译失败或需要修改 Shell/Python 脚本、Makefile 替换正则及配置文件时，**必须且唯一在本地搭建极简仿真环境（Python/Shell 单机 Mock 单元测试与语法校验）**。
- **100% 验证无误后再提交**：必须在本地实测验证修改后的正则表达式、脚本输出和文本替换逻辑 100% 符合预期后，方可 Commit 并 Push 到 GitHub Actions，绝对严禁任何未经本地仿真验证的云端盲目试错！
