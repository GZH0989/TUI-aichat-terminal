#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# ai-terminal 安装脚本 (Linux / macOS)
# ═══════════════════════════════════════════════════════════
# 用法：
#   bash install.sh
#
# 特点：
#   - 所有内容安装到脚本所在目录，不污染系统
#   - 生成 ai-term 启动器，可随时移动文件夹
#   - 幂等：重复运行不会破坏已有环境
# ═══════════════════════════════════════════════════════════

set -euo pipefail

# 脚本所在目录 = 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"
CONFIG="$SCRIPT_DIR/config.toml"
CHAT_DIR="$SCRIPT_DIR/chat"
LAUNCHER="$SCRIPT_DIR/ai-term"

# ── 输出工具 ────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[FAIL]${NC} $*" >&2; }

# ── 前置检查 ────────────────────────────────────────────
info "检查 Python 环境..."

if ! command -v python3 >/dev/null 2>&1; then
    error "未找到 python3。请先安装："
    error "  sudo apt install python3 python3-venv"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python 版本：$PY_VER"

if ! python3 -c 'import venv' >/dev/null 2>&1; then
    error "Python 缺少 venv 模块。请安装："
    error "  sudo apt install python3-venv"
    exit 1
fi

if ! python3 -c 'import tomllib' >/dev/null 2>&1; then
    error "Python 版本过低（需要 3.11+，因为使用了 tomllib）。"
    error "  当前版本：$PY_VER"
    error "  Ubuntu 22.04 请升级到 24.04，或手动安装新版 Python。"
    exit 1
fi

# ── 检查主程序 ──────────────────────────────────────────
if [[ ! -f "$SCRIPT_DIR/ai_terminal.py" ]]; then
    error "未找到 ai_terminal.py，请把它放到本脚本同一目录。"
    exit 1
fi

# ── 创建虚拟环境 ────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    info "虚拟环境已存在，跳过创建"
else
    info "创建虚拟环境（$VENV_DIR）..."
    python3 -m venv "$VENV_DIR"
    ok "虚拟环境已创建"
fi

# ── 安装依赖 ────────────────────────────────────────────
info "安装依赖（aiohttp, prompt_toolkit）..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet aiohttp prompt_toolkit
ok "依赖安装完成"

# ── chat 目录 ──────────────────────────────────────────
mkdir -p "$CHAT_DIR"
ok "chat/ 目录已就绪"

# ── 生成启动器 ──────────────────────────────────────────
cat > "$LAUNCHER" <<'LAUNCHER_EOF'
#!/bin/bash
# ai-terminal 启动器
# 自动解析自身位置，调用同目录下的 venv 和主程序。
# 整个文件夹可以任意移动，无需修改任何路径。
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/venv/bin/python" "$DIR/ai_terminal.py" "$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"
ok "已生成启动器：$LAUNCHER"

# ── 完成 ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  安装完成${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "安装位置：$SCRIPT_DIR"
echo ""
echo "接下来三步："
echo ""
echo "  1. 填入 API key："
echo "       nano $CONFIG"
echo "     把 api_key = \"\" 改成 api_key = \"sk-你的密钥\""
echo ""
echo "  2. 启动："
echo "       $SCRIPT_DIR/ai-term"
echo ""
echo "  （可选）想在任何目录用 ai-term 命令："
echo "       echo \"alias ai-term='$SCRIPT_DIR/ai-term'\" >> ~/.bashrc"
echo "       source ~/.bashrc"
echo ""
