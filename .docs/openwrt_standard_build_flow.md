# OpenWRT / ImmortalWRT 标准构建链路与架构指南

本文档全面梳理 OpenWRT / ImmortalWRT 的底层标准构建链路（Build Architecture）、依赖图逻辑（DAG & Topological Sort）、各阶段核心机制以及 CI 自动化避坑实践。

---

## 一、 构建链路总揽 (Architecture Overview)

OpenWRT 的构建系统基于 GNU Make、Kconfig 与自定义 Shell 脚本构建。完整的编译流程分为 6 个严格阶段：

```
[ Phase 1: Feeds ]    ---> [ Phase 2: Kconfig ]     ---> [ Phase 3: Host Tools ]
  - feeds update             - merge GENERAL.txt            - tools/compile
  - feeds install            - make defconfig               - staging_dir/host/

                                                                    |
                                                                    v

[ Phase 6: Image ]     <--- [ Phase 5: Packages ]   <--- [ Phase 4: Toolchain ]
  - kernel compile           - DAG Topological Sort         - gcc / binutils
  - SquashFS / ext4          - compile to staging_dir       - musl / glibc
  - sysupgrade.bin           - generate .ipk / .apk         - staging_dir/toolchain/
```

---

## 二、 阶段详解 (Phase Deep Dive)

### 1. 软件源与 Feed 管理阶段 (`scripts/feeds`)

* **核心指令**：
  ```bash
  ./scripts/feeds update -a    # 从 feeds.conf.default 下载第三方仓库索引
  ./scripts/feeds install -a   # 在 package/feeds/<feed>/ 下建立符号链接
  ```
* **运行机制**：
  Feed 仓库源码位于根目录 `feeds/` 下。执行 `install -a` 后，系统会在 `package/feeds/<feed_name>/<pkg_name>` 创建软链接，指向 `feeds/` 中的物理文件。
* **开发规范**：
  自定义插件或对第三方仓库的修改，必须在 `feeds install -a` 之后执行（例如在 `Scripts/Packages.sh` 或 `Scripts/Handles.sh` 中处理）。

---

### 2. 配置生成与 Kconfig 阶段 (`make defconfig`)

* **核心指令**：
  ```bash
  cat Config/IPQ60XX-WIFI-YES.txt Config/GENERAL.txt >> .config
  make defconfig -j$(nproc)
  ```
* **运行机制**：
  * `make defconfig` 逐行扫描 `.config`，根据包 Makefile 中的 `select` 与 `depends on` 以及目标平台的 `DEVICE_PACKAGES` 自动补全必要依赖、推导矛盾依赖。
  * 自动将配置格式化为标准的 `CONFIG_PACKAGE_<name>=y` 或 `=n`，并写入 `.config` 与 `include/config/`。

---

### 3. 宿主编译工具链构建 (`tools/`)

* **核心目录**：`tools/` ➡️ 产出到 `staging_dir/host/`
* **运行机制**：
  构建宿主机运行的编译辅助工具（如 `patch`、`sed`、`cmake`、`flock`、`findutils`、`go-bootstrap`、`zstd` 等）。
* **重要结论**：
  宿主工具是后续交叉编译的基础。全量 `make` 会按顺序先构建 `tools/`。

---

### 4. 目标架构交叉工具链构建 (`toolchain/`)

* **核心目录**：`toolchain/` ➡️ 产出到 `staging_dir/toolchain-<arch>_gcc-*/`
* **运行机制**：
  * 构建目标芯片架构（例如高通 `aarch64_cortex-a53`）的 C 库（`musl` 或 `glibc`）。
  * 编译交叉编译器 `aarch64-openwrt-linux-musl-gcc` 及 Binutils 工具链。

---

### 5. 软件包编译与 Staging 阶段 (`package/`)

这是最核心、也是最容易出现依赖死锁的阶段。

#### 5.1 有向无环图与拓扑排序 (DAG & Topological Sort)
OpenWRT 依靠 Makefile 中的 `DEPENDS:=` 声明构建依赖拓扑图：

```makefile
# 示例：avahi Makefile 声明
define Package/avahi-dbus-daemon
  TITLE:=Avahi daemon (D-Bus)
  DEPENDS:=+libdaemon +libexpat +libdbus
endef
```

1. **依赖顺序推导**：OpenWRT 依靠 `tsort` 解析 `DEPENDS:=+libdaemon`，推导出 `libdaemon` 必须优先于 `avahi` 编译。
2. **Staging 产物释放**：
   - 步骤 A：`libdaemon` 优先编译，将其 C 头文件（`.h`）安装到 `staging_dir/target-aarch64_musl/usr/include/`，将动态库（`.so`）安装到 `staging_dir/target-aarch64_musl/usr/lib/`。
   - 步骤 B：`avahi` 开始编译，它的 `./configure` 和 `gcc` 自动在 `staging_dir/target-aarch64_musl/` 中寻找到 `libdaemon` 的头文件与库文件，完成顺利编译。
3. **打包 .ipk / .apk**：编译完成后，产物会被打包进 `bin/packages/<arch>/`。

---

### 6. 内核编译与固件打包阶段 (`target/linux/`)

* **核心目录**：`target/linux/<target_name>/`
* **运行机制**：
  1. 编译 Linux 内核（例如高通 `qualcommax` 6.18 内核）。
  2. 加载高通 NSS 硬件加速驱动与 BDF 校准文件。
  3. 收集所有已选中的 `.ipk` / `.apk` 包，解压合并生成 RootFS。
  4. 使用 `mksquashfs` 生成 SquashFS 镜像，并追加 DTB 设备树。
  5. 按照设备的 `IMAGE/factory.bin := append-kernel | pad-to $(KERNEL_SIZE) | append-rootfs` 拼接出最终固件。

---

## 三、 硬件物理分区表对齐与内核 GZIP 瘦身机制 (Flash Partition & GZIP Standards)

在针对实体路由器（如京东云雅典娜 RE-CS-02、亚瑟 RE-SS-01 等 eMMC 存储设备）进行固件打包时，必须严苛遵循以下物理存储与解压引擎规范：

### 1. `KERNEL_SIZE` 物理偏移量铁律 (6MB 物理对齐)
* 在 OpenWrt 镜像生成宏中，`pad-to $(KERNEL_SIZE)` 充当了**内核与根文件系统（RootFS）之间的物理偏移基准**。
* 雅典娜路由器的 eMMC 硬件 GPT 分区表中给 `kernel` 分区分配的物理空间正好是 **`6144k` (6MB)**。
* **物理绝杀禁忌**：严禁为了规避编译期 `Build/check-size` 的超限告警而盲目加大 `KERNEL_SIZE`（如改到 32MB）。改大 `KERNEL_SIZE` 会用 0 字节硬填充到 32MB 之后才追加 `rootfs`，导致路由器 Bootloader 在 6MB 偏移处寻址 `rootfs` 失败而引发 Kernel Panic、死机、无 Wi-Fi。

### 2. 原厂 U-Boot 唯一支持解压引擎：GZIP (`CONFIG_KERNEL_GZIP=y`)
* 雅典娜物理路由器原厂 Bootloader（U-Boot）的 bootm 引擎**仅支持 GZIP 解压算法，绝对不支持 LZMA/XZ**！强改 LZMA 会直接导致路由器无法开机。
* **无损瘦身正统解法**：保持 `CONFIG_KERNEL_GZIP=y`，通过在 `.config` 中关闭臃肿的内核调试符号：
  ```config
  # CONFIG_KERNEL_DEBUG_INFO is not set
  # CONFIG_KERNEL_DEBUG_INFO_BTF is not set
  ```
* **效果**：使 GZIP 压缩的 FIT 内核体积稳定控制在 **~4.8MB**（低于 6MB 分区上限 1.2MB），在保持物理分区表 100% 对齐的前提下，实现秒级引导开机亮蓝灯！

---

## 四、 黄金准则与避坑指南 (Best Practices & Anti-Patterns)

### ❌ 禁忌一：在 Profile 配置文件中手动硬写 `kmod-` 选单破坏 Kconfig 依赖树
* **错误原理**：在 `IPQ60XX-WIFI-YES.txt` 等配置文件中人为写 `CONFIG_PACKAGE_kmod-ath11k=y` / `kmod-mac80211=y` 等选单，会触发 OpenWrt 的“用户自定义覆盖”逻辑，直接跳过 Target 层（`qualcommax`）设备定义中的 `DEVICE_PACKAGES` 自动拓扑补齐，导致漏掉 `/etc/modules.d/mac80211` 引导索引与 `qca-nss-drv-wifi-meshmgr` 硬件加速符号。
* **正确做法**：严格遵循标杆仓库 [VIKINGYFY/OpenWRT-CI](https://github.com/VIKINGYFY/OpenWRT-CI) 规范，Profile 保持极简 3 行架构，完全由 OpenWrt 官方 Target 依赖自动解算。

### ❌ 禁忌二：引入依赖 Nginx 的插件强刷 HTTP 302 重定向
* **错误原理**：勾选 `luci-app-quickfile` 会强制引入 `Nginx` 替换 `uhttpd`，并利用 `/etc/config/nginx` 的 `_redirect2ssl` 强下发 302 重定向。用 `sed` 硬改临时配置文件违背 Rule 16 官方规范。
* **正确做法**：源头取消 `quickfile`，保留轻量 `luci-app-filetransfer`，100% 回归 OpenWrt 官方原生 `uhttpd` 服务。

### ❌ 禁忌三：盲目篡改 `KERNEL_SIZE` 分区偏移或强替换 LZMA 算法
* **错误原理**：改动 `KERNEL_SIZE` 会破坏物理 GPT 分区表对齐；强用 LZMA 会导致原厂 U-Boot 无法解压开机。
* **正确做法**：保持原厂 `KERNEL_SIZE := 6144k` 物理分区表与 `GZIP` 算法不变，通过关闭 `DEBUG_INFO` 无损瘦身至 ~4.8MB。

### ❌ 禁忌四：盲目用 `sed` 抹除 Makefile 中的 `DEPENDS:=+pkg`
* **错误原理**：抹除 `DEPENDS` 声明会导致 OpenWRT 丢掉依赖拓扑关系，在依赖库（如 `libdaemon`）尚未编译进 `staging_dir` 时就提前开始编译目标包（如 `avahi`），触发 GCC 头文件缺失报错。
* **正确做法**：遇到缺失的依赖包，通过 `Packages.sh` 使用 `UPDATE_PACKAGE` 克隆补齐源码，让 OpenWRT 自动完成拓扑排序。

### ❌ 禁忌五：Shell `sed` 修改 Makefile 时忽视 TAB 制表符
* **错误原理**：OpenWrt Makefile 语法规定 `define` 内部变量前使用 TAB 制表符 (`\t`) 缩进。硬编码空格的 `sed` 无法匹配开头的 `\t`，会导致修补静默失效。
* **正确做法**：使用兼容 TAB 和空格的扩展正则表达式（`-E 's/([[:space:]]*VAR[[:space:]]*:=).*/.../g'`）。

### ❌ 禁忌六：同名包或基础版/增强版包冲突
* **错误原理**：同时选择 `dnsmasq` 和 `dnsmasq-full` 会在打包阶段触发 `Package collision` 报错。
* **正确做法**：开启增强版时，显式关闭基础版（如 `CONFIG_PACKAGE_dnsmasq=n`）。

---

## 五、 总结与参考规范

OpenWRT 构建系统的灵魂在于 **“拓扑依赖图 (DAG) 自动驱动”**、**“遵守原厂 U-Boot GZIP/6MB 物理规范”** 与 **“官方正规 Kconfig 规范优先”**。保证依赖包源码齐全、内核依靠关闭 DEBUG 符号无损瘦身、保持 Profile 配置极简对齐上游标杆，是确保固件在真实物理路由器上 100% 成功刷入与运行的核心钥匙。
