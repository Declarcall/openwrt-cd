#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 VIKINGYFY

#移除luci-app-attendedsysupgrade
sed -i "/attendedsysupgrade/d" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改默认主题
sed -i "s/luci-theme-bootstrap/luci-theme-$WRT_THEME/g" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改immortalwrt.lan关联IP
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $(find ./feeds/luci/modules/luci-mod-system/ -type f -name "flash.js")
#添加编译日期标识
sed -i "s/(\(luciversion || ''\))/(\1) + (' \/ $WRT_MARK-$WRT_DATE')/g" $(find ./feeds/luci/modules/luci-mod-status/ -type f -name "10_system.js")

WIFI_SH=$(find ./target/linux/{mediatek/filogic,qualcommax}/base-files/etc/uci-defaults/ -type f -name "*set-wireless.sh" 2>/dev/null)
WIFI_UC="./package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc"
if [ -f "$WIFI_SH" ]; then
	#修改WIFI名称
	sed -i "s/BASE_SSID='.*'/BASE_SSID='$WRT_SSID'/g" $WIFI_SH
	#修改WIFI密码
	sed -i "s/BASE_WORD='.*'/BASE_WORD='$WRT_WORD'/g" $WIFI_SH
elif [ -f "$WIFI_UC" ]; then
	#修改WIFI名称
	sed -i "s/ssid='.*'/ssid='$WRT_SSID'/g" $WIFI_UC
	#修改WIFI密码
	sed -i "s/key='.*'/key='$WRT_WORD'/g" $WIFI_UC
fi

# 开启默认 Wi-Fi 发射状态 (开机默认直接发射 Wi-Fi 信号，无需手动开启)
sed -i "s/disabled='1'/disabled='0'/g" $WIFI_SH 2>/dev/null || true
sed -i "s/disabled=1/disabled=0/g" $WIFI_UC 2>/dev/null || true

CFG_FILE="./package/base-files/files/bin/config_generate"
#修改默认IP地址
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $CFG_FILE
#修改默认主机名
sed -i "s/hostname='.*'/hostname='$WRT_NAME'/g" $CFG_FILE


#配置文件修改
echo "CONFIG_PACKAGE_luci=y" >> ./.config
echo "CONFIG_LUCI_LANG_zh_Hans=y" >> ./.config
echo "CONFIG_PACKAGE_luci-theme-$WRT_THEME=y" >> ./.config
echo "CONFIG_PACKAGE_luci-app-$WRT_THEME-config=y" >> ./.config

#引入私有扩展配置
if [ -f "$GITHUB_WORKSPACE/Config/PRIVATE.txt" ]; then
	echo "Applying private configurations from PRIVATE.txt..."
	cat $GITHUB_WORKSPACE/Config/PRIVATE.txt >> ./.config
fi

#手动调整的插件
if [ -n "$WRT_PACKAGE" ]; then
	echo -e "$WRT_PACKAGE" >> ./.config
fi

#无WIFI配置标志
if [[ "${WRT_CONFIG,,}" == *"wifi"* && "${WRT_CONFIG,,}" == *"no"* ]]; then
	echo "WRT_WIFI=wifi-no" >> $GITHUB_ENV
fi

#高通平台调整
DTS_PATH="./target/linux/qualcommax/dts/"
if [[ "${WRT_TARGET^^}" == *"QUALCOMMAX"* ]] || [ -d "./target/linux/qualcommax" ]; then
	# 正规标准做法：在 target/linux/ 的 config-* 模板中显式并完整对齐 DEBUG_INFO & DEBUG_FS 的 Choice 选单所有反选项
	find ./target/linux/ -name "config-*" -exec sed -i "/CONFIG_DEBUG_INFO/d" {} + 2>/dev/null || true
	find ./target/linux/ -name "config-*" -exec sed -i "/CONFIG_DEBUG_FS/d" {} + 2>/dev/null || true
	find ./target/linux/ -name "config-*" -exec bash -c '
		echo "CONFIG_DEBUG_INFO_NONE=y" >> "$1"
		echo "# CONFIG_DEBUG_INFO is not set" >> "$1"
		echo "# CONFIG_DEBUG_INFO_BTF is not set" >> "$1"
		echo "# CONFIG_DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT is not set" >> "$1"
		echo "# CONFIG_DEBUG_INFO_DWARF4 is not set" >> "$1"
		echo "# CONFIG_DEBUG_INFO_DWARF5 is not set" >> "$1"
		echo "# CONFIG_DEBUG_FS is not set" >> "$1"
		echo "CONFIG_DEBUG_FS_ALLOW_NONE=y" >> "$1"
		echo "# CONFIG_DEBUG_FS_ALLOW_ALL is not set" >> "$1"
		echo "# CONFIG_DEBUG_FS_DISALLOW_MOUNT is not set" >> "$1"
	' _ {} \; 2>/dev/null || true

	#无WIFI配置调整Q6大小
	if [[ "${WRT_CONFIG,,}" == *"wifi"* && "${WRT_CONFIG,,}" == *"no"* ]]; then
		find $DTS_PATH -type f ! -iname '*nowifi*' -exec sed -i 's/ipq\(6018\|8074\).dtsi/ipq\1-nowifi.dtsi/g' {} +
		echo "qualcommax set up nowifi successfully!"
	fi
fi
