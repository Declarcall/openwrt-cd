#!/usr/bin/env python3
import sys
import re

def patch_kernel_defaults(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    # 在 Kernel/CompileImage/Default 的 rm vmlinux 紧后强行注入 non-interactive oldconfig
    p = r"(rm -f \$\(LINUX_DIR\)/vmlinux \$\(LINUX_DIR\)/System\.map)"
    r = r'\1\n\tyes "" | $(KERNEL_MAKEOPTS) oldconfig'
    text = re.sub(p, r, text)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "./include/kernel-defaults.mk"
    patch_kernel_defaults(target)
