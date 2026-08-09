# 📑 OpenWRT-CI 历史踩坑与失败经验全景总结报告

> **项目核心目标**：确保生成的固件能在真实物理路由器（雅典娜 RE-CS-02）的原版 U-Boot 下 100% 成功刷入、物理分区对齐、顺畅引导开机、包含 iStore 商店与多主题支持，且 Wi-Fi 与硬件加速全开。

---

## 一、 Wi-Fi 驱动加载失败与无线搜不到（Wi-Fi Driver & Kernel Symbol Failures）

### ❌ 历史失败现象
刷入固件开机后，手机搜不到 Wi-Fi 信号，后台没有“无线”选单。在终端运行 `dmesg` 或 `insmod ath11k.ko` 时提示 `RET:255` 或 `Unknown symbol ath11k_core_alloc (err -2)`。

### 🔍 失败根源分析
1. **人为手写 `kmod-` 选单破坏 Kconfig 依赖树**：
   * 在 `IPQ60XX-WIFI-YES.txt` 中人为写入了 `CONFIG_PACKAGE_kmod-ath11k=y` / `kmod-mac80211=y` 等驱动选单。
   * OpenWrt 的 Kconfig 机制规定：**一旦用户在 `.config` 中人为手写了子驱动，系统会判定“用户接管驱动管理”，从而直接跳过 Target 层（`qualcommax`）设备定义中的 `DEVICE_PACKAGES` 自动拓扑补齐**。
   * 结果导致系统漏掉了 `/etc/modules.d/mac80211` 引导索引以及 `qca-nss-drv-wifi-meshmgr.ko` 硬件加速符号文件。
2. **物理开机崩溃与 CI 静态 Log 假相**：
   * 云端 CI 的静态日志检查只校验 `.config` 是否有 `=y` 和 `.ko` 文件是否被编译出来。
   * 虽然 `ath11k.ko` 被打包进了固件，但在物理机开机那一刻，由于找不到 NSS 硬件加速符号，驱动在 Linux 内核层抛出 `ERR:-2` 拒绝加载。`ath11k` 挂掉后，系统 `/etc/board.json` 留空，`mac80211.uc` 放弃生成 `/etc/config/wireless`。

### ✅ 正确解法与金标准 (Rule 14 & Rule 16)
* **100% 对齐标杆仓库**：Profile 配置文件 [Config/IPQ60XX-WIFI-YES.txt](file:///home/joefom/Public/gitpro/openwrt-ci-test/openwrt-cd/Config/IPQ60XX-WIFI-YES.txt) **保持极简 3 行架构**：
  ```config
  CONFIG_TARGET_qualcommax=y
  CONFIG_TARGET_qualcommax_ipq60xx=y
  CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02=y
  ```
* 绝不手动手写 `kmod-` 选单干预，完全放权给 OpenWrt 官方 Target 层原生自动解算与打包雅典娜全套驱动与固件！

---

## 二、 Web 后台强制重定向 HTTPS 与“不安全”警告（Web Engine & HTTP/HTTPS Redirect Issues）

### ❌ 历史失败现象
在浏览器敲 `http://192.168.10.1` 访问后台时，浏览器立刻自动跳转到 `https://192.168.10.1`，并弹出红色的 `Not secure` / `Your connection isn't private` 警告。即便在 LuCI 后台取消勾选“重定向至 HTTPS”，在新开的无痕窗口中依然会被强制重定向。

### 🔍 失败根源分析
1. **插件强塞 Nginx 替换了 uhttpd**：
   * 配置文件中勾选了 **Quick 文件管理 (`luci-app-quickfile`)**。
   * `quickfile` 的 Makefile 显式声明了 `DEPENDS:=+nginx +nginx-mod-luci`，强行将 Web 引擎从默认的 `uhttpd` 替换为了 `Nginx`。
2. **Nginx 出厂配置硬编码 302**：
   * `Nginx` 在 `/etc/config/nginx` 中默认生成了一个 `_redirect2ssl` 模块，监听 80 端口并抛出 `302 https://$host$request_uri` 强制跳转。
   * 浏览器接收到 302 或 HSTS Header 后，将其永久写入 Chromium 底层 HSTS 安全策略表，导致即便在无痕模式下输入 `http://` 也会在浏览器内部被拦截转换。
3. **应急 `sed` 硬补丁违背规范**：
   * 之前尝试用 `sed` 强改 `uhttpd.config` 或植入 `99_` 脚本，不仅没有解决 Nginx 占用的问题，还违背了 Rule 16 的规范原则。

### ✅ 正确解法与金标准 (Rule 16)
* **源头净化 Web 引擎**：在 [Config/GENERAL.txt](file:///home/joefom/Public/gitpro/openwrt-ci-test/openwrt-cd/Config/GENERAL.txt) 中彻底取消勾选 `luci-app-quickfile`，清除 `Nginx` 依赖。
* **回归原生 uhttpd**：系统 100% 回归 OpenWrt 官方原生 `uhttpd`，保留轻量级文件管理 `luci-app-filetransfer`。出厂默认绝不下发 302 / HSTS，保证 `http://192.168.10.1` 纯净访问。

---

## 三、 iStore 应用商店及后台服务丢失（iStore App Store Missing）

### ❌ 历史失败现象
刷入固件后，后台首页和菜单栏找不到 **iStore 软件商店** 的入口。在终端运行 `apk info` 只能找到 `taskd`，找不到 `luci-app-store`。

### 🔍 失败根源分析
1. **源码克隆漏掉前端仓库**：
   * 在 `Config/GENERAL.txt` 中写入了 `CONFIG_PACKAGE_luci-app-store=y`。
   * 但在 `Scripts/Packages.sh` 脚本中，仅拉取了后端服务仓库 `linkease/nas-packages`（提供 `taskd`），**漏掉了真正存放 iStore 网页前端界面的官方仓库 `linkease/istore`**。
2. **编译器的静默丢弃逻辑**：
   * OpenWrt 在 `make defconfig` 时找不到 `luci-app-store` 的 `Makefile`，判定该插件源码不存在，便静默丢弃了该行配置，导致界面未被编译进固件。

### ✅ 正确解法与金标准
* 在 [Scripts/Packages.sh](file:///home/joefom/Public/gitpro/openwrt-ci-test/openwrt-cd/Scripts/Packages.sh#L85) 中显式引入官方前端仓库：
  ```bash
  UPDATE_PACKAGE "istore" "linkease/istore" "main" "name"
  ```
* 确保前端 UI 与后台 `taskd` 依赖一同拉取并打包进固件。

---

## 四、 主题选项单调与多主题缺失（Multi-Theme Selection Issues）

### ❌ 历史失败现象
进入 **系统 -> 系统属性 -> 语言和界面 -> 主题** 下拉菜单，发现只有一个 `Aurora` 主题可选，无法切换到经典的 `Argon` 或 `Kucat` 主题。

### 🔍 失败根源分析
* `Scripts/Settings.sh` 中设置了默认主题 `WRT_THEME=aurora`。
* 但在 `Config/GENERAL.txt` 中没有把 `Argon`、`Kucat`、`Design` 等主题写入勾选清单，编译器只打包了 `Aurora` 一个主题文件。

### ✅ 正确解法与金标准
* 在 [Config/GENERAL.txt](file:///home/joefom/Public/gitpro/openwrt-ci-test/openwrt-cd/Config/GENERAL.txt#L60-L71) 中全量勾选热门主题：
  ```config
  CONFIG_PACKAGE_luci-theme-argon=y
  CONFIG_PACKAGE_luci-app-argon-config=y
  CONFIG_PACKAGE_luci-theme-kucat=y
  CONFIG_PACKAGE_luci-app-kucat-config=y
  CONFIG_PACKAGE_luci-theme-aurora=y
  CONFIG_PACKAGE_luci-app-aurora-config=y
  CONFIG_PACKAGE_luci-theme-noobwrt=y
  CONFIG_PACKAGE_luci-theme-design=y
  ```
* 实现出厂默认 `Aurora`，后台菜单支持 5+ 款主流主题自由无缝切换。

---

## 五、 原厂 U-Boot 物理规范与磁盘瘦身（Physical Flash Safeguards）

### ❌ 历史风险点
雅典娜路由器（IPQ6018）采用原厂物理 U-Boot，其物理 GPT 分区表中的 `KERNEL_SIZE` 严格限定为 **`6144k` (6MB)**，且 Bootm 解压引擎**只支持 GZIP 算法**。如果内核编译过大或改用 LZMA 算法，刷入后将直接导致路由器变砖死机。

### ✅ 物理防护铁律 (Rule 9 & Rule 13)
1. **解压算法锁定 GZIP**：`CONFIG_KERNEL_GZIP=y`，绝对严禁强行替换为 U-Boot 不支持的 LZMA/XZ。
2. **分区大小锁定 6144k**：物理分区表 `KERNEL_SIZE` 锁定 `6144k`，严禁篡改分区偏移。
3. **内核无损瘦身**：通过关闭臃肿的 `CONFIG_KERNEL_DEBUG_INFO` 与 `CONFIG_KERNEL_DEBUG_INFO_BTF`，将 GZIP 内核精准控制在 **~4.8MB**（低于 6MB 分区上限 1.2MB），实现秒级开机亮蓝灯！

---

## 🎯 总结与黄金铁律

| 维度 | 曾用非标准方式（踩坑） | 标杆正规化方式（成功） |
| :--- | :--- | :--- |
| **Wi-Fi 驱动配置** | 在 Profile 中手写 `kmod-ath11k` / `kmod-mac80211` 破坏依赖树 | Profile 保持极简 3 行，100% 遵从官方 Target 依赖自动解算 |
| **Web HTTP 服务** | 引入 `quickfile` 强塞 Nginx，写 `sed` 硬改配置文件 | 剔除 `quickfile` 净化 Nginx，100% 回归官方原生 `uhttpd` |
| **iStore 商店** | 只拉取后端 `nas-packages`，漏掉前端 UI 仓库 | 补齐 `linkease/istore` 官方前端源码，前后端同步打包 |
| **主题丰富度** | 仅打包单一 `Aurora` 主题 | 全量打包 Argon / Kucat / Aurora / Design / NoobWrt 5 大主题 |
| **物理引导与瘦身** | 无 | 锁定 6MB GZIP 分区规范，关闭 DEBUG_INFO 瘦身至 ~4.8MB |
