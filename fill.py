#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填充脚本
=========
把 src/ai_terminal.py 和 src/README.md 嵌入 installer_template.py，
生成 一键安装修复脚本.py。

用法:
    python fill.py

目录要求:
    src/ai_terminal.py      主程序源码
    src/README.md           README 源码
    installer_template.py   填充样板（包含占位符）
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR / "src"
TEMPLATE_PATH = SCRIPT_DIR / "installer_template.py"
OUTPUT_PATH = SCRIPT_DIR / "一键安装修复脚本.py"

PLACEHOLDER_MAIN = "@@AI_TERMINAL_PY@@"
PLACEHOLDER_README = "@@README_MD@@"


def read_source(path, label):
    """读取源文件，做安全检查。"""
    if not path.exists():
        sys.stderr.write("[错误] 找不到文件: %s\n" % path)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    # 检查三引号冲突（内嵌字符串用 r'''...''' 包裹）
    if "'''" in text:
        sys.stderr.write(
            "[错误] %s 中包含 '''，会破坏内嵌的 r'''...''' 字符串。\n"
            "       请先替换或转义这些三引号，再重新运行 fill.py。\n" % label
        )
        sys.exit(1)

    # 检查末尾反斜杠（原始字符串不能以反斜杠结尾）
    if text.endswith("\\"):
        sys.stderr.write(
            "[错误] %s 以反斜杠结尾，无法安全嵌入到 r'''...''' 中。\n"
            "       请在文件末尾加一个空行再试。\n" % label
        )
        sys.exit(1)

    return text


def main():
    if not TEMPLATE_PATH.exists():
        sys.stderr.write("[错误] 找不到模板: %s\n" % TEMPLATE_PATH)
        sys.exit(1)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    if PLACEHOLDER_MAIN not in template:
        sys.stderr.write("[错误] 模板缺少占位符: %s\n" % PLACEHOLDER_MAIN)
        sys.exit(1)
    if PLACEHOLDER_README not in template:
        sys.stderr.write("[错误] 模板缺少占位符: %s\n" % PLACEHOLDER_README)
        sys.exit(1)

    print("读取源文件...")
    ai_terminal = read_source(SRC_DIR / "ai_terminal.py", "src/ai_terminal.py")
    readme = read_source(SRC_DIR / "README.md", "src/README.md")
    print("  ai_terminal.py: %d 字符" % len(ai_terminal))
    print("  README.md:      %d 字符" % len(readme))

    print("填充模板...")
    output = template.replace(PLACEHOLDER_MAIN, ai_terminal)
    output = output.replace(PLACEHOLDER_README, readme)

    # 简单语法校验
    try:
        compile(output, str(OUTPUT_PATH), "exec")
    except SyntaxError as e:
        sys.stderr.write(
            "[错误] 生成的脚本有语法错误，可能源文件含特殊字符。\n"
            "       位置: line %s, col %s\n"
            "       信息: %s\n" % (e.lineno, e.offset, e.msg)
        )
        sys.exit(1)

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print()
    print("已生成: %s" % OUTPUT_PATH)
    print("  总大小: %d 字符" % len(output))


if __name__ == "__main__":
    main()
