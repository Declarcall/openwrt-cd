#!/usr/bin/env python3
import sys
import re

def patch_kernel_mk(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    # 1. 注入 CONFIG_DEBUG_INFO_NONE=y 到 .config.target 生成阶段
    p1 = r"(awk .*CONFIG_KERNEL.*\.config\.target)"
    r1 = r'\1\n\techo "CONFIG_DEBUG_INFO_NONE=y" >> $(LINUX_DIR)/.config.target\n\tsed -i "s/CONFIG_DEBUG_INFO=y/# CONFIG_DEBUG_INFO is not set/g" $(LINUX_DIR)/.config.target'
    text = re.sub(p1, r1, text)

    # 2. 替换 multi-line cmp -s 逻辑块，无条件强行注入 olddefconfig 自动结算
    p2 = r"cmp -s \$\(LINUX_DIR\)/\.config\.set \$\(LINUX_DIR\)/\.config\.prev \|\| \{[\s\S]*?\}"
    r2 = "\tcp $(LINUX_DIR)/.config.set $(LINUX_DIR)/.config\n\t$(KERNEL_MAKEOPTS) olddefconfig\n\tcp $(LINUX_DIR)/.config $(LINUX_DIR)/.config.prev"
    text = re.sub(p2, r2, text)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "./include/kernel-build.mk"
    patch_kernel_mk(target)
