#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 问答终端 (TTY)
运行环境: Ubuntu Server LTS 26.04
最小尺寸: 6 行 x 80 列

焦点循环 (7 个):
    输出区 → 输入框 → API → Model → 思考 → 问题导航 → 历史对话 → 输出区

按键:
    ↑↓          切换焦点
    ←→          当前控件内操作（移动光标/滚动/预览选值）
    Enter       确认/发送
    Ctrl+Enter  输入框内换行
    Esc         中断当前流式请求
    Ctrl+R      热重载 config.toml
    Ctrl+C      保存并退出

思考强度: none(关) / low(低) / high(高) / max(最高)

网络策略:
    1. 大读取超时（sock_read=600s），避免思考期间被误判为超时
    2. TCP keepalive socket 选项，及时感知物理连接断开
    3. 忽略 SSE 注释行（以 ":" 开头），它们是服务端心跳

安全：所有流式内容与本地历史读取都会经过 strip_control_chars，
防止模型输出的 ANSI 转义序列被终端误解释。
"""

import asyncio
import json
import os
import re
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

import aiohttp
from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style

# ═══════════════════════════════════════════════════════════════
# 路径与默认配置
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.toml"
CHAT_DIR = SCRIPT_DIR / "chat"
CHAT_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG_TOML = r"""# ═══════════════════════════════════════════════════════════
# AI 终端配置文件
# 修改后按 Ctrl+R 热重载（不丢失当前对话）
# ═══════════════════════════════════════════════════════════

[ui]
# 终端最小宽度（列）。低于此值显示可能不正常。
min_width = 80

# 流式回答时是否自动滚动到底部。
auto_scroll = true


[defaults]
# 启动时默认使用的 API 和模型（名称须在下方 [[apis]] 中存在）。
api = "deepseek"
model = "deepseek-reasoner"

# 启动时“思考强度”默认档位。
# 可选: "none"(关) / "low"(低) / "high"(高) / "max"(最高)
reasoning_effort = "high"


[context]
# 历史对话的 token 预算。只保留最近这个数量以内发给 API。
max_tokens = 32000

# 是否将思考过程回传给 API。
# true  = 回传（走兼容网关或加工具调用时必须为 true）
# false = 不回传（纯问答直连官方 API 时推荐，省 token）
passthrough_reasoning = false

# 自动摘要开关。
auto_summarize = false

# 摘要触发阈值（占 max_tokens 的比例）。0.8 = 80%。
summarize_threshold = 0.8


# ── 网络 ─────────────────────────────────────────────────
[network]
# 单次请求的读取超时（秒）。思考模型可能长时间不发数据，
# 这个值决定“多久没收到新数据就认为超时”。
sock_read_timeout = 600

# 建立连接的超时（秒）。
connect_timeout = 30

# TCP keepalive 的空闲探测启动时间（秒）。
# 物理连接断开时用于快速感知。
tcp_keepidle = 30

# TCP keepalive 探测间隔（秒）。
tcp_keepintvl = 10

# TCP keepalive 探测次数。超过这个次数没响应就认为连接已断。
tcp_keepcnt = 3


# ── API 配置 ─────────────────────────────────────────────
[[apis]]
name = "deepseek"
base_url = "https://api.deepseek.com/v1"
api_key = ""
api_key_env = "DEEPSEEK_API_KEY"
models = ["deepseek-reasoner", "deepseek-chat"]

# ── 添加更多 API ─────────────────────────────────────────
# 只要兼容 OpenAI Chat Completions 协议，都可以加 [[apis]]。
# 字段说明：
#   name        显示名（自定义）
#   base_url    API 端点（末尾不带 /）
#   api_key     明文密钥（方便）  ─┐
#   api_key_env 环境变量名（安全） ─┴ 二选一，api_key 优先
#   models      可用模型列表
#
# 例如 Moonshot：
# [[apis]]
# name = "moonshot"
# base_url = "https://api.moonshot.cn/v1"
# api_key = "sk-xxx"
# models = ["moonshot-v1-128k"]

[[apis]]
name = "openai"
base_url = "https://api.openai.com/v1"
api_key = ""
api_key_env = "OPENAI_API_KEY"
models = ["gpt-4o", "gpt-4o-mini"]
"""

if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass

import tomllib  # noqa: E402  (Python 3.11+)


def load_config():
    """读取 TOML 配置。语法错误会抛出异常，由调用方处理。"""
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def validate_config(cfg):
    """
    校验配置结构。返回错误信息字符串；无错误则返回空串。
    只做“不崩就行”的最低限度检查。
    """
    if not isinstance(cfg, dict):
        return "配置文件格式错误：根节点必须是表"
    apis = cfg.get("apis")
    if not apis or not isinstance(apis, list):
        return "配置里没有任何 [[apis]]，请至少配置一个 API"
    for i, a in enumerate(apis):
        if not isinstance(a, dict):
            return "[[apis]] 第 %d 项不是表" % (i + 1)
        if not a.get("name"):
            return "[[apis]] 第 %d 项缺少 name" % (i + 1)
        if not a.get("base_url"):
            return "[[apis]] %s 缺少 base_url" % a.get("name", "?")
        models = a.get("models")
        if not models or not isinstance(models, list):
            return "[[apis]] %s 缺少 models" % a.get("name", "?")
    return ""


# 启动时加载并校验配置。失败时给友好提示，不静默崩溃。
try:
    CONFIG = load_config()
except Exception as e:
    sys.stderr.write(
        "\n[错误] 无法读取 config.toml: %s\n"
        "       请修复该文件，或删除后重新运行以生成默认配置。\n\n" % e
    )
    sys.exit(1)

_err = validate_config(CONFIG)
if _err:
    sys.stderr.write("\n[错误] %s\n\n" % _err)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

# 思考强度档位，顺序即显示顺序
THINK_LEVELS = ["none", "low", "high", "max"]
THINK_LABELS = {"none": "关", "low": "低", "high": "高", "max": "最高"}

# ═══════════════════════════════════════════════════════════════
# 通用工具函数
# ═══════════════════════════════════════════════════════════════

# 匹配除 \t(0x09)、\n(0x0a) 以外的所有 C0 控制字符 + DEL(0x7f)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def strip_control_chars(s):
    """
    剔除控制字符，防止模型输出的 ANSI 转义序列被终端误解释。
    保留 \t 和 \n。
    """
    if not s:
        return ""
    return _CTRL_RE.sub('', s)


def term_size():
    """返回 (列, 行)，无 TTY 时回退到 80x24。"""
    s = shutil.get_terminal_size(fallback=(80, 24))
    return s.columns, s.lines


def char_width(ch):
    """CJK 字符显示宽度为 2，其他为 1。"""
    return 2 if ord(ch) > 0x2E80 else 1


def str_width(s):
    """字符串的显示宽度。"""
    return sum(char_width(c) for c in s)


def wrap_text(text, width):
    """按显示宽度硬换行，保留原有的 \n。"""
    if width <= 0:
        return [text]
    result = []
    for para in text.split("\n"):
        if not para:
            result.append("")
            continue
        line = ""
        w = 0
        for ch in para:
            cw = char_width(ch)
            if w + cw > width:
                result.append(line)
                line, w = ch, cw
            else:
                line += ch
                w += cw
        result.append(line)
    return result


def estimate_tokens(text):
    """粗略估算 token 数：约 1 token ≈ 1.5 字符。"""
    if not text:
        return 0
    return int(len(text) / 1.5) + 1


def get_api_key(api):
    """优先读 api_key 字段，为空时回退到环境变量 api_key_env。"""
    k = (api.get("api_key") or "").strip()
    if k:
        return k
    env_name = api.get("api_key_env") or ""
    if env_name:
        return os.environ.get(env_name, "")
    return ""


def _ft_multi(rows):
    """
    rows: List[List[(style, text)]]
    每个内层 list 是一行的片段序列（用于一行内多段样式）。
    在每行最后一个片段末尾（除最后一行）加 \n。
    """
    result = []
    n = len(rows)
    for i, line in enumerate(rows):
        if not line:
            if i < n - 1:
                result.append(("", "\n"))
            continue
        m = len(line)
        for j, (style, text) in enumerate(line):
            if j == m - 1 and i < n - 1:
                text = text + "\n"
            result.append((style, text))
    return FormattedText(result)


def _pad_to(text, width):
    """右侧补空格到指定宽度（用于状态栏占满整行）。"""
    w = str_width(text)
    if w < width:
        text += " " * (width - w)
    return text


def _truncate(s, w):
    """按显示宽度截断，末尾加省略号。"""
    if str_width(s) <= w:
        return s
    out = ""
    cur = 0
    for ch in s:
        cw = char_width(ch)
        if cur + cw > w - 1:
            break
        out += ch
        cur += cw
    return out + "…"


def _fmt_tokens(n):
    """把 token 数格式化：1234 -> '1.2k'，12345 -> '12.3k'，123 -> '123'。"""
    if n is None:
        return "?"
    if n < 1000:
        return str(n)
    return f"{n/1000:.1f}k"


# ═══════════════════════════════════════════════════════════════
# 网络层：TCP keepalive socket 工厂
# ═══════════════════════════════════════════════════════════════

def _keepalive_socket_factory(addr_info):
    """
    aiohttp 的 socket_factory 钩子，用来在 socket 上启用 TCP keepalive。
    addr_info 是 socket.getaddrinfo() 返回的 5 元组。
    """
    family, socktype, proto, canonname, sockaddr = addr_info
    sock = socket.socket(family, socktype, proto)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Linux 特有的 TCP keepalive 参数
        if sys.platform.startswith("linux"):
            net = CONFIG.get("network", {})
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_KEEPIDLE,
                    int(net.get("tcp_keepidle", 30)),
                )
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_KEEPINTVL,
                    int(net.get("tcp_keepintvl", 10)),
                )
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_KEEPCNT,
                    int(net.get("tcp_keepcnt", 3)),
                )
    except OSError:
        # 某些平台不支持这些选项，静默降级
        pass
    sock.setblocking(False)
    return sock


def _make_session():
    """
    创建 aiohttp ClientSession，配置：
    - 大 sock_read 超时，避免思考期间被误判
    - TCP keepalive，及时感知物理断开
    """
    net = CONFIG.get("network", {})
    timeout = aiohttp.ClientTimeout(
        total=None,                                          # 不限制总时长
        connect=int(net.get("connect_timeout", 30)),
        sock_connect=int(net.get("connect_timeout", 30)),
        sock_read=int(net.get("sock_read_timeout", 600)),
    )
    try:
        connector = aiohttp.TCPConnector(socket_factory=_keepalive_socket_factory)
    except (TypeError, AttributeError):
        # 老版本 aiohttp 不支持 socket_factory，降级
        connector = aiohttp.TCPConnector()
    return aiohttp.ClientSession(timeout=timeout, connector=connector)


# ═══════════════════════════════════════════════════════════════
# 输入缓冲区
# ═══════════════════════════════════════════════════════════════

class InputBuffer:
    """纯文本 + 光标位置。按字符操作，不涉及显示宽度。"""
    def __init__(self):
        self.text = ""
        self.cursor = 0

    def insert(self, s):
        self.text = self.text[:self.cursor] + s + self.text[self.cursor:]
        self.cursor += len(s)

    def backspace(self):
        if self.cursor > 0:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1

    def delete(self):
        if self.cursor < len(self.text):
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]

    def left(self):
        if self.cursor > 0:
            self.cursor -= 1

    def right(self):
        if self.cursor < len(self.text):
            self.cursor += 1

    def home(self):
        self.cursor = 0

    def end(self):
        self.cursor = len(self.text)

    def clear(self):
        self.text = ""
        self.cursor = 0


# ═══════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════

FOCUS_OUTPUT = 0
FOCUS_INPUT  = 1
FOCUS_API    = 2
FOCUS_MODEL  = 3
FOCUS_THINK  = 4
FOCUS_NAV    = 5
FOCUS_HIST   = 6
N_FOCUS = 7


class State:
    def __init__(self):
        # ── 对话内容 ──
        self.messages = []
        self.qa_blocks = []
        self.view_blocks = None
        self.view_path = None

        # ── 视口 ──
        self.viewport_offset = 0
        self.follow_output = True

        # ── 流式 ──
        self.streaming = False
        self.abort_event = asyncio.Event()
        self.thinking_buf = ""
        self.answer_buf = ""
        self.in_thinking = True
        self.active_block = None

        # ── 焦点 ──
        self.focus = FOCUS_INPUT

        # ── API ──
        defaults = CONFIG.get("defaults", {})
        default_api = defaults.get("api", "")
        default_model = defaults.get("model", "")
        self.api_idx = 0
        self.model_idx = 0
        for i, a in enumerate(CONFIG["apis"]):
            if a["name"] == default_api:
                self.api_idx = i
                models = a.get("models", [])
                if default_model in models:
                    self.model_idx = models.index(default_model)
                break

        # ── 预览值 ──
        self.api_preview = None
        self.model_preview = None
        self.reasoning_preview = None

        # ── 思考强度（生效值，str） ──
        eff = defaults.get("reasoning_effort", "high")
        if eff not in THINK_LEVELS:
            eff = "high"
        self.reasoning_effort = eff

        # ── token 用量（从 API 上报） ──
        self.last_usage = None

        # ── 导航 / 历史 ──
        self.nav_idx = 0
        self.history_files = []
        self.history_idx = 0
        self.current_chat_path = None

        # ── 输入 ──
        self.input = InputBuffer()

        # ── 状态栏通知（重载错误等） ──
        self.notice = ""

    def current_api(self):
        return CONFIG["apis"][self.api_idx]

    def current_model_name(self):
        models = self.current_api().get("models", [])
        if not models:
            return ""
        return models[self.model_idx]

    def display_blocks(self):
        return self.view_blocks if self.view_blocks is not None else self.qa_blocks

    def is_viewing_history(self):
        return self.view_blocks is not None

    def reasoning_on(self):
        return self.reasoning_effort != "none"


state = State()


def revalidate_state_after_reload():
    """
    config.toml 重载后，把 state 里的索引、预览、档位校正到合法范围。
    避免因配置项增删导致的 IndexError。
    """
    apis = CONFIG.get("apis", [])
    if not apis:
        return
    if state.api_idx < 0 or state.api_idx >= len(apis):
        state.api_idx = 0
        state.model_idx = 0
    models = apis[state.api_idx].get("models", [])
    if not models:
        state.model_idx = 0
    elif state.model_idx < 0 or state.model_idx >= len(models):
        state.model_idx = 0
    if state.reasoning_effort not in THINK_LEVELS:
        state.reasoning_effort = "high"

    # 预览值一律重置
    state.api_preview = None
    state.model_preview = None
    state.reasoning_preview = None

    # 历史索引校正
    if state.history_idx >= len(state.history_files):
        state.history_idx = max(0, len(state.history_files) - 1)

    # 导航索引校正
    blocks = state.display_blocks()
    if state.nav_idx >= len(blocks):
        state.nav_idx = max(0, len(blocks) - 1) if blocks else 0


# ═══════════════════════════════════════════════════════════════
# 对话文件存储
# ═══════════════════════════════════════════════════════════════

def new_chat():
    """
    创建新的对话文件。文件名精确到毫秒，冲突时追加序号，
    避免同一秒内多次启动时互相覆盖。
    """
    now = datetime.now()
    base = now.strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]  # 毫秒精度
    path = CHAT_DIR / f"{base}.json"
    counter = 1
    while path.exists():
        path = CHAT_DIR / f"{base}_{counter}.json"
        counter += 1

    data = {
        "created": now.isoformat(timespec="seconds"),
        "updated": now.isoformat(timespec="seconds"),
        "api": "",
        "model": "",
        "messages": [],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    state.current_chat_path = path
    state.messages = []
    return path


def save_current_chat():
    if not state.current_chat_path or not state.messages:
        return
    try:
        created = json.loads(
            state.current_chat_path.read_text(encoding="utf-8")
        ).get("created")
    except Exception:
        created = datetime.now().isoformat(timespec="seconds")

    data = {
        "created": created,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "api": state.current_api()["name"] if CONFIG.get("apis") else "",
        "model": state.current_model_name(),
        "messages": state.messages,
    }
    tmp = state.current_chat_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(state.current_chat_path)


def delete_current_if_empty():
    if state.current_chat_path and not state.messages:
        try:
            state.current_chat_path.unlink(missing_ok=True)
        except Exception:
            pass


# 只清理符合本程序命名规则的对话文件，避免误删用户手动放进来的 JSON
_CHAT_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d{3})?(_\d+)?\.json$")


def cleanup_empty_chats(keep_path=None):
    """
    删除 chat/ 目录下、符合本程序命名规则、且 messages 为空的对话文件。
    keep_path: 保留这个路径不删（通常是刚创建的当前对话）。
    """
    for p in CHAT_DIR.glob("*.json"):
        if not _CHAT_FILE_RE.match(p.name):
            continue
        if keep_path is not None and p == keep_path:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            # 解析失败的跳过，不冒险删
            continue
        if not data.get("messages"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


def refresh_history():
    files = sorted(CHAT_DIR.glob("*.json"), reverse=True)
    state.history_files = files
    if state.history_idx >= len(files):
        state.history_idx = max(0, len(files) - 1)


_title_cache = {}


def get_file_title(path):
    key = str(path)
    if key in _title_cache:
        return _title_cache[key]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        title = ""
        for m in data.get("messages", []):
            if m.get("role") == "user":
                title = strip_control_chars(m.get("content", "")).replace("\n", " ")[:30]
                break
        if not title:
            title = path.stem
    except Exception:
        title = path.stem
    _title_cache[key] = title
    return title


def load_history_to_view(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    messages = data.get("messages", [])
    blocks = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "user":
            i += 1
            continue
        q = strip_control_chars(msg.get("content", ""))
        think = ""
        ans = ""
        if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
            think = strip_control_chars(messages[i + 1].get("reasoning_content", ""))
            ans = strip_control_chars(messages[i + 1].get("content", ""))
            i += 2
        else:
            i += 1
        blocks.append({
            "question": q,
            "q_lines": None,
            "think_lines": None,
            "ans_lines": None,
            "think_collapsed": True,
            "done": True,
            "raw_think": think,
            "raw_ans": ans,
        })
    state.view_blocks = blocks
    state.view_path = path
    state.viewport_offset = 0
    state.follow_output = False
    state.nav_idx = 0


def exit_view_mode():
    state.view_blocks = None
    state.view_path = None
    state.viewport_offset = 0
    state.follow_output = True
    state.nav_idx = 0


# ═══════════════════════════════════════════════════════════════
# LLM 调用（流式）
# ═══════════════════════════════════════════════════════════════

def build_api_messages(user_text):
    """
    构造发送给 API 的消息数组，处理思考回传和 token 截断。
    passthrough_reasoning = true 时，reasoning_content 也会计入预算。
    """
    msgs = list(state.messages)
    msgs.append({"role": "user", "content": user_text.strip()})

    passthrough = bool(CONFIG.get("context", {}).get("passthrough_reasoning", False))
    if not passthrough:
        cleaned = []
        for m in msgs:
            if m.get("role") == "assistant" and "reasoning_content" in m:
                cleaned.append({"role": "assistant", "content": m["content"]})
            else:
                cleaned.append(m)
        msgs = cleaned

    def _msg_tokens(m):
        n = estimate_tokens(m.get("content", "") or "")
        if passthrough and m.get("reasoning_content"):
            n += estimate_tokens(m["reasoning_content"])
        return n

    budget = int(CONFIG.get("context", {}).get("max_tokens", 32000))
    total = sum(_msg_tokens(m) for m in msgs)
    while total > budget and len(msgs) > 2:
        dropped = msgs.pop(0)
        total -= _msg_tokens(dropped)
    return msgs


async def call_api_summary(msgs):
    """非流式摘要调用（供 auto_summarize 使用）。"""
    api = state.current_api()
    model = state.current_model_name()
    url = api["base_url"].rstrip("/") + "/chat/completions"
    key = get_api_key(api)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    text = "\n".join(f"{m['role']}: {m['content']}" for m in msgs if "content" in m)
    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "把以下对话历史压缩成简洁摘要，保留用户需求、约束、文件名/路径、结论。"
                        "不添加新信息。中文回答。"},
            {"role": "user", "content": text},
        ],
        "stream": False,
    }
    async with _make_session() as session:
        async with session.post(url, headers=headers, json=payload) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]


async def maybe_summarize():
    if not CONFIG.get("context", {}).get("auto_summarize", False):
        return
    budget = int(CONFIG.get("context", {}).get("max_tokens", 32000))
    threshold = float(CONFIG.get("context", {}).get("summarize_threshold", 0.8))
    total = sum(estimate_tokens(m.get("content", "")) for m in state.messages)
    if total < budget * threshold:
        return
    if len(state.messages) < 4:
        return
    half = len(state.messages) // 2
    early = state.messages[:half]
    try:
        summary = await call_api_summary(early)
        state.messages = [
            {"role": "system", "content": f"[前文摘要] {summary}"}
        ] + state.messages[half:]
    except Exception:
        pass


async def stream_llm(user_text, on_think, on_content, on_done):
    """
    流式请求 LLM。回调：
        on_think(chunk)    思考内容增量
        on_content(chunk)  回答内容增量
        on_done()          结束（正常或异常都会调用）

    网络策略:
        - _make_session() 提供大读取超时 + TCP keepalive
        - SSE 注释行（":" 开头）被忽略，它们是服务端心跳
        - payload 里带 stream_options.include_usage，让 API 上报 token 用量
    """
    if not CONFIG.get("apis"):
        on_content("[错误] 配置里没有任何 API。请检查 config.toml。")
        on_done()
        return

    api = state.current_api()
    model = state.current_model_name()
    if not model:
        on_content("[错误] 当前 API 的 models 列表为空。请在 config.toml 里至少配置一个模型。")
        on_done()
        return

    key = get_api_key(api)
    if not key:
        env_hint = api.get("api_key_env", "") or "(未指定)"
        on_content(f"[错误] 未配置 API key：请在 config.toml 的 [[apis]] 填写 api_key，"
                   f"或设置环境变量 {env_hint}")
        on_done()
        return

    url = api["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    payload = {
        "model": model,
        "messages": build_api_messages(user_text),
        "stream": True,
        # 让 API 在流末上报 token 用量
        "stream_options": {"include_usage": True},
    }
    # 只有开启思考时才发送 reasoning_effort，避免部分网关对 "none" 报 400
    if state.reasoning_on():
        payload["reasoning_effort"] = state.reasoning_effort

    # 记录本次请求的推理状态，供解析时决定是否处理 reasoning_content
    reasoning_on = state.reasoning_on()

    try:
        async with _make_session() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    on_content(f"\n[HTTP {resp.status}] {err[:300]}")
                    on_done()
                    return

                async for raw in resp.content:
                    if state.abort_event.is_set():
                        break

                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        continue

                    # SSE 注释行（服务端心跳），忽略
                    if line.startswith(":"):
                        continue

                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        obj = json.loads(data)

                        # 解析 token 用量（通常出现在最后一个块）
                        usage = obj.get("usage")
                        if usage:
                            state.last_usage = usage

                        choices = obj.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            if reasoning_on:
                                rc = delta.get("reasoning_content")
                                if rc:
                                    on_think(rc)
                            c = delta.get("content", "")
                            if c:
                                on_content(c)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except asyncio.TimeoutError:
        on_content(
            f"\n[超时] 服务端在 "
            f"{CONFIG.get('network', {}).get('sock_read_timeout', 600)} 秒内"
            f"未发送新数据。如果模型确实在长时间思考，请在 config.toml 的 [network] "
            f"里调大 sock_read_timeout。"
        )
    except aiohttp.ClientError as e:
        on_content(f"\n[连接错误] {type(e).__name__}: {e}")
    except Exception as e:
        on_content(f"\n[网络错误] {type(e).__name__}: {e}")
    on_done()


# ═══════════════════════════════════════════════════════════════
# 输出区渲染
# ═══════════════════════════════════════════════════════════════

def materialize_block(blk, width):
    if blk.get("q_lines") is None:
        blk["q_lines"] = wrap_text(blk["question"], max(10, width - 6))
    if blk.get("raw_think") is not None and blk.get("think_lines") is None:
        rt = blk["raw_think"]
        blk["think_lines"] = wrap_text(rt, max(10, width - 8)) if rt else []
    if blk.get("raw_ans") is not None and blk.get("ans_lines") is None:
        ra = blk["raw_ans"]
        blk["ans_lines"] = wrap_text(ra, max(10, width - 6)) if ra else []


def build_output_lines(width):
    lines = []
    blocks = state.display_blocks()
    is_view = state.is_viewing_history()

    for blk in blocks:
        materialize_block(blk, width)

        for i, l in enumerate(blk["q_lines"]):
            prefix = " Q: " if i == 0 else "    "
            lines.append(("q", f"{prefix}{l}"))

        think_lines = blk.get("think_lines") or []
        if blk.get("done", True):
            if think_lines:
                if blk.get("think_collapsed", False):
                    lines.append(("think",
                                  f" ▶ 思考过程（{len(think_lines)} 行，Enter 展开）"))
                else:
                    lines.append(("think", " ▼ 思考过程"))
                    for l in think_lines:
                        lines.append(("think", f"   │ {l}"))
                    lines.append(("think", "   └── 思考结束 ──"))
        else:
            lines.append(("think", " ● 思考中…（Esc 中断）"))
            for l in think_lines:
                lines.append(("think", f"   │ {l}"))

        ans_lines = blk.get("ans_lines") or []
        for i, l in enumerate(ans_lines):
            prefix = " A: " if i == 0 else "    "
            lines.append(("ans", f"{prefix}{l}"))

        lines.append(("", ""))

    if is_view:
        lines.append(("hint", " ── 正在查看历史对话（输入框已禁用，↑↓ 换焦点）──"))
        lines.append(("", ""))

    return lines


def get_output_text():
    width, height = term_size()
    out_h = max(1, height - 3)

    lines = build_output_lines(width)
    total = len(lines)
    max_off = max(0, total - out_h)

    if state.follow_output:
        off = max_off
    else:
        off = min(state.viewport_offset, max_off)
    state.viewport_offset = off

    visible = lines[off:off + out_h]
    while len(visible) < out_h:
        visible.append(("", ""))

    focus_here = (state.focus == FOCUS_OUTPUT)
    bar_char = "▌" if focus_here else " "
    bar_style = "class:bar" if focus_here else "class:output-blur"
    bg_style = "class:output-focused" if focus_here else "class:output-blur"

    rows = []
    for style, text in visible:
        content_style = f"{bg_style} class:{style}" if style else bg_style
        rows.append([
            (bar_style, bar_char),
            (content_style, " " + text),
        ])
    return _ft_multi(rows)


# ═══════════════════════════════════════════════════════════════
# 输入区渲染
# ═══════════════════════════════════════════════════════════════

_input_cache = {"key": None, "lines": None, "cur_line": 0, "cur_char_idx": 0}


def compute_input_lines():
    width, _ = term_size()
    key = (state.input.text, state.input.cursor, width, state.focus,
           state.streaming, state.view_blocks is not None)
    if _input_cache["key"] == key:
        return _input_cache

    text = state.input.text
    cursor = state.input.cursor

    prompt = ">>> "
    cont = "    "
    prompt_w = 4
    cont_w = 4

    raw_lines = []
    line = prompt
    line_w = prompt_w
    cur_line = 0
    cur_char_idx = 4

    for i, ch in enumerate(text):
        cw = char_width(ch)
        if line_w + cw > width:
            raw_lines.append(line)
            line, line_w = cont, cont_w
        if i == cursor:
            cur_line = len(raw_lines)
            cur_char_idx = len(line)
        line += ch
        line_w += cw

    if cursor == len(text):
        if line_w + 1 > width:
            raw_lines.append(line)
            line, line_w = cont, cont_w
        cur_line = len(raw_lines)
        cur_char_idx = len(line)
    raw_lines.append(line)

    while len(raw_lines) < 2:
        raw_lines.append(cont)

    if len(raw_lines) > 2:
        start = min(max(0, cur_line - 1), len(raw_lines) - 2)
        visible = raw_lines[start:start + 2]
        cur_line -= start
    else:
        visible = raw_lines

    _input_cache["key"] = key
    _input_cache["lines"] = visible
    _input_cache["cur_line"] = cur_line
    _input_cache["cur_char_idx"] = cur_char_idx
    return _input_cache


def get_input_text():
    c = compute_input_lines()
    focused = (state.focus == FOCUS_INPUT)

    if state.is_viewing_history():
        st_prompt = "class:prompt-blur"
        st_content = "class:input-disabled"
    elif focused:
        st_prompt = "class:prompt-focused"
        st_content = "class:input-focused"
    else:
        st_prompt = "class:prompt-blur"
        st_content = "class:input-blur"

    rows = []
    for line_idx, line in enumerate(c["lines"]):
        prompt_part = line[:4]
        body = line[4:]

        if focused and line_idx == c["cur_line"]:
            body_idx = c["cur_char_idx"] - 4
            body_idx = max(0, min(body_idx, len(body)))

            body_before = body[:body_idx]
            if body_idx < len(body):
                cursor_char = body[body_idx]
                body_after = body[body_idx + 1:]
            else:
                cursor_char = " "
                body_after = ""

            rows.append([
                (st_prompt, prompt_part),
                (st_content, body_before),
                ("class:cursor-block", cursor_char),
                (st_content, body_after),
            ])
        else:
            rows.append([
                (st_prompt, prompt_part),
                (st_content, body),
            ])
    return _ft_multi(rows)


# ═══════════════════════════════════════════════════════════════
# 底部状态栏渲染
# ═══════════════════════════════════════════════════════════════

def _token_str():
    """返回 token 用量文本，没有则返回空字符串。"""
    u = state.last_usage
    if not u:
        return ""
    pt = u.get("prompt_tokens", 0)
    ct = u.get("completion_tokens", 0)
    tt = u.get("total_tokens", pt + ct)
    return f" Tokens:{_fmt_tokens(pt)}↑/{_fmt_tokens(ct)}↓/{_fmt_tokens(tt)}∑ "


def render_compact(width):
    """未聚焦底部控件时的紧凑栏。"""
    # 有通知时优先显示（重载错误、配置警告等）
    if state.notice:
        text = " ⚠ " + state.notice
        text = _truncate(text, width)
        return FormattedText([("class:status-warn", _pad_to(text, width))])

    api_name = state.current_api()["name"] if CONFIG.get("apis") else "(无)"
    model_name = state.current_model_name() or "(无)"
    effort_label = THINK_LABELS.get(state.reasoning_effort, state.reasoning_effort)

    parts = [
        ("class:status-effective", f" {api_name}:{model_name} "),
        ("class:status", f" 思考:{effort_label} "),
    ]

    blocks = state.display_blocks()
    if blocks:
        idx = min(state.nav_idx, len(blocks) - 1)
        parts.append(("class:status", f" [{idx + 1}/{len(blocks)}] "))

    if state.history_files:
        idx = min(state.history_idx, len(state.history_files) - 1)
        is_cur = state.history_files[idx] == state.current_chat_path
        star = "★" if is_cur else ""
        parts.append(("class:status", f" [{idx + 1}/{len(state.history_files)}{star}] "))

    parts.append(("class:status", " ↑↓切换 · Enter发送 · Ctrl+C退出 "))

    used = sum(str_width(t) for _, t in parts)

    # token 用量右对齐
    tok = _token_str()
    tok_w = str_width(tok)
    if tok and used + tok_w <= width:
        parts.append(("class:status-token", " " * (width - used - tok_w) + tok))
    elif used < width:
        parts.append(("class:status", " " * (width - used)))

    return FormattedText(parts)


def render_api_full(width):
    apis = CONFIG.get("apis", [])
    if not apis:
        text = " ◀ API：[无可用 API，请检查 config.toml] ▶    ↑↓ 换控件 "
        return FormattedText([("class:status-warn", _pad_to(_truncate(text, width), width))])

    effective = state.api_idx
    preview = state.api_preview if state.api_preview is not None else effective
    preview = max(0, min(preview, len(apis) - 1))
    preview_name = apis[preview]["name"]
    is_diff = (preview != effective)

    bracket_style = "class:status-bracket-yellow" if is_diff else "class:status-bracket-blue"

    parts = [
        ("class:status-active", " ◀ API: "),
        (bracket_style, f"[{preview_name}]"),
        ("class:status-active", " ▶    ←→ 选值 · Enter 确认   ↑↓ 换控件 "),
    ]
    used = sum(str_width(t) for _, t in parts)
    if used < width:
        parts.append(("class:status-active", " " * (width - used)))
    return FormattedText(parts)


def render_model_full(width):
    api = state.current_api() if CONFIG.get("apis") else None
    models = (api or {}).get("models", [])
    if not models:
        text = " ◀ Model：[当前 API 未配置模型] ▶    ↑↓ 换控件 "
        return FormattedText([("class:status-warn", _pad_to(_truncate(text, width), width))])

    effective = state.model_idx
    preview = state.model_preview if state.model_preview is not None else effective
    preview = max(0, min(preview, len(models) - 1))
    preview_name = models[preview]
    is_diff = (preview != effective)

    bracket_style = "class:status-bracket-yellow" if is_diff else "class:status-bracket-blue"

    parts = [
        ("class:status-active", " ◀ Model: "),
        (bracket_style, f"[{preview_name}]"),
        ("class:status-active", " ▶    ←→ 选值 · Enter 确认   ↑↓ 换控件 "),
    ]
    used = sum(str_width(t) for _, t in parts)
    if used < width:
        parts.append(("class:status-active", " " * (width - used)))
    return FormattedText(parts)


def render_think_level_full(width):
    """
    思考强度多档选择控件。
    视觉语言:
        亮色 + [ ] = 生效值 + 光标位置重合
        亮色无括号 = 生效值但不是光标
        黄底 = 光标位置，且 != 生效值（预览中）
        暗色 = 既不是生效值也不是光标
    """
    effective = state.reasoning_effort
    preview = state.reasoning_preview if state.reasoning_preview is not None else effective
    if preview not in THINK_LEVELS:
        preview = effective

    parts = [("class:status-active", " ◀ 思考强度: ")]
    for lvl in THINK_LEVELS:
        label = THINK_LABELS[lvl]
        is_effective = (lvl == effective)
        is_cursor = (lvl == preview)

        if is_effective and is_cursor:
            text = f"[{label}]"
            style = "class:status-bracket-blue"
        elif is_effective:
            text = f" {label} "
            style = "class:status-effective"
        elif is_cursor:
            text = f"[{label}]"
            style = "class:status-bracket-yellow"
        else:
            text = f" {label} "
            style = "class:status-dim"
        parts.append((style, text))

    parts.append(("class:status-active", "    ←→ 选档 · Enter 确认   ↑↓ 换控件 "))
    used = sum(str_width(t) for _, t in parts)
    if used < width:
        parts.append(("class:status-active", " " * (width - used)))
    return FormattedText(parts)


def render_nav_full(width):
    blocks = state.display_blocks()
    if not blocks:
        text = " ◀ 问题导航：[无问答] ▶     ↑↓ 换控件 "
        return FormattedText([("class:status-active", _pad_to(text, width))])

    idx = min(state.nav_idx, len(blocks) - 1)
    q = blocks[idx]["question"].replace("\n", " ")
    q = _truncate(q, max(10, width - 30))
    text = f" ◀ 问题导航：[{idx + 1}/{len(blocks)}] {q} ▶    ←→ 翻页 · Enter 跳转 "
    return FormattedText([("class:status-active", _pad_to(text, width))])


def render_history_full(width):
    files = state.history_files
    if not files:
        text = " ◀ 历史对话：[无历史文件] ▶     ↑↓ 换控件 "
        return FormattedText([("class:status-active", _pad_to(text, width))])

    idx = min(state.history_idx, len(files) - 1)
    path = files[idx]
    is_cur = (path == state.current_chat_path)
    suffix = " <当前>" if is_cur else ""
    title = get_file_title(path)
    label = f"{title}{suffix}"
    text = f" ◀ 历史对话：[{idx + 1}/{len(files)}] {label} ▶    ←→ 翻页 · Enter 加载 "
    return FormattedText([("class:status-active", _pad_to(text, width))])


def get_status_text():
    width, _ = term_size()
    if state.focus == FOCUS_API:
        return render_api_full(width)
    if state.focus == FOCUS_MODEL:
        return render_model_full(width)
    if state.focus == FOCUS_THINK:
        return render_think_level_full(width)
    if state.focus == FOCUS_NAV:
        return render_nav_full(width)
    if state.focus == FOCUS_HIST:
        return render_history_full(width)
    return render_compact(width)


# ═══════════════════════════════════════════════════════════════
# 提问流程
# ═══════════════════════════════════════════════════════════════

async def submit_query():
    text = state.input.text.strip()
    if not text or state.streaming or state.is_viewing_history():
        return
    if not CONFIG.get("apis"):
        return

    state.input.clear()

    blk = {
        "question": text,
        "q_lines": None,
        "think_lines": None,
        "ans_lines": None,
        "think_collapsed": False,
        "done": False,
    }
    state.qa_blocks.append(blk)
    state.active_block = blk
    state.nav_idx = len(state.qa_blocks) - 1

    state.streaming = True
    state.abort_event.clear()
    state.thinking_buf = ""
    state.answer_buf = ""
    state.in_thinking = True
    state.follow_output = True

    app = get_app()
    app.invalidate()

    await maybe_summarize()

    width = term_size()[0]
    think_chunks = []
    ans_chunks = []

    def on_think(chunk):
        think_chunks.append(strip_control_chars(chunk))
        state.thinking_buf = "".join(think_chunks)
        blk["think_lines"] = wrap_text(state.thinking_buf, max(10, width - 8))
        app.invalidate()

    def on_content(chunk):
        clean_chunk = strip_control_chars(chunk)
        if state.in_thinking:
            state.in_thinking = False
            blk["think_lines"] = (wrap_text(state.thinking_buf, max(10, width - 8))
                                  if state.thinking_buf else [])
        ans_chunks.append(clean_chunk)
        state.answer_buf = "".join(ans_chunks)
        blk["ans_lines"] = wrap_text(state.answer_buf, max(10, width - 6))
        app.invalidate()

    def on_done():
        blk["think_lines"] = (wrap_text(state.thinking_buf, max(10, width - 8))
                              if state.thinking_buf else [])
        blk["ans_lines"] = wrap_text(state.answer_buf, max(10, width - 6))
        blk["done"] = True

        state.messages.append({"role": "user", "content": text})
        entry = {"role": "assistant", "content": state.answer_buf}
        if state.thinking_buf:
            entry["reasoning_content"] = state.thinking_buf
        state.messages.append(entry)

        state.streaming = False
        state.thinking_buf = ""
        state.answer_buf = ""
        state.in_thinking = True
        state.active_block = None

        try:
            save_current_chat()
        except Exception:
            pass
        refresh_history()
        app.invalidate()

    await stream_llm(text, on_think, on_content, on_done)


# ═══════════════════════════════════════════════════════════════
# 按键绑定
# ═══════════════════════════════════════════════════════════════

kb = KeyBindings()


def in_input():
    return state.focus == FOCUS_INPUT and not state.is_viewing_history()


def clear_previews():
    state.api_preview = None
    state.model_preview = None
    state.reasoning_preview = None


def on_focus_enter(new_focus):
    if new_focus == FOCUS_API:
        state.api_preview = state.api_idx
    elif new_focus == FOCUS_MODEL:
        state.model_preview = state.model_idx
    elif new_focus == FOCUS_THINK:
        state.reasoning_preview = state.reasoning_effort


@kb.add("up")
def _(event):
    clear_previews()
    state.notice = ""
    state.focus = (state.focus - 1) % N_FOCUS
    on_focus_enter(state.focus)
    event.app.invalidate()


@kb.add("down")
def _(event):
    clear_previews()
    state.notice = ""
    state.focus = (state.focus + 1) % N_FOCUS
    on_focus_enter(state.focus)
    event.app.invalidate()


@kb.add("left")
def _(event):
    f = state.focus
    if f == FOCUS_OUTPUT:
        state.follow_output = False
        state.viewport_offset = max(0, state.viewport_offset - 1)
    elif f == FOCUS_INPUT:
        state.input.left()
    elif f == FOCUS_API:
        apis = CONFIG.get("apis", [])
        if apis:
            n = len(apis)
            if state.api_preview is None:
                state.api_preview = state.api_idx
            state.api_preview = (state.api_preview - 1) % n
    elif f == FOCUS_MODEL:
        api = state.current_api() if CONFIG.get("apis") else None
        models = (api or {}).get("models", [])
        if models:
            n = len(models)
            if state.model_preview is None:
                state.model_preview = state.model_idx
            state.model_preview = (state.model_preview - 1) % n
    elif f == FOCUS_THINK:
        if state.reasoning_preview is None:
            state.reasoning_preview = state.reasoning_effort
        if state.reasoning_preview not in THINK_LEVELS:
            state.reasoning_preview = state.reasoning_effort
        idx = THINK_LEVELS.index(state.reasoning_preview)
        state.reasoning_preview = THINK_LEVELS[(idx - 1) % len(THINK_LEVELS)]
    elif f == FOCUS_NAV:
        if state.display_blocks():
            state.nav_idx = max(0, state.nav_idx - 1)
    elif f == FOCUS_HIST:
        if state.history_files:
            state.history_idx = max(0, state.history_idx - 1)
    event.app.invalidate()


@kb.add("right")
def _(event):
    f = state.focus
    if f == FOCUS_OUTPUT:
        width, height = term_size()
        out_h = max(1, height - 3)
        total = len(build_output_lines(width))
        max_off = max(0, total - out_h)
        if state.viewport_offset >= max_off - 1:
            state.follow_output = True
        else:
            state.follow_output = False
            state.viewport_offset += 1
    elif f == FOCUS_INPUT:
        state.input.right()
    elif f == FOCUS_API:
        apis = CONFIG.get("apis", [])
        if apis:
            n = len(apis)
            if state.api_preview is None:
                state.api_preview = state.api_idx
            state.api_preview = (state.api_preview + 1) % n
    elif f == FOCUS_MODEL:
        api = state.current_api() if CONFIG.get("apis") else None
        models = (api or {}).get("models", [])
        if models:
            n = len(models)
            if state.model_preview is None:
                state.model_preview = state.model_idx
            state.model_preview = (state.model_preview + 1) % n
    elif f == FOCUS_THINK:
        if state.reasoning_preview is None:
            state.reasoning_preview = state.reasoning_effort
        if state.reasoning_preview not in THINK_LEVELS:
            state.reasoning_preview = state.reasoning_effort
        idx = THINK_LEVELS.index(state.reasoning_preview)
        state.reasoning_preview = THINK_LEVELS[(idx + 1) % len(THINK_LEVELS)]
    elif f == FOCUS_NAV:
        blocks = state.display_blocks()
        if blocks:
            state.nav_idx = min(len(blocks) - 1, state.nav_idx + 1)
    elif f == FOCUS_HIST:
        if state.history_files:
            state.history_idx = min(len(state.history_files) - 1, state.history_idx + 1)
    event.app.invalidate()


@kb.add("enter")
def _(event):
    f = state.focus

    if f == FOCUS_OUTPUT:
        blocks = state.display_blocks()
        if blocks:
            idx = min(state.nav_idx, len(blocks) - 1)
            blk = blocks[idx]
            blk["think_collapsed"] = not blk.get("think_collapsed", False)

    elif f == FOCUS_INPUT:
        if state.is_viewing_history() or state.streaming:
            return
        asyncio.ensure_future(submit_query())

    elif f == FOCUS_API:
        apis = CONFIG.get("apis", [])
        if apis and state.api_preview is not None:
            new_idx = max(0, min(state.api_preview, len(apis) - 1))
            if new_idx != state.api_idx:
                state.api_idx = new_idx
                state.model_idx = 0
            state.api_preview = state.api_idx

    elif f == FOCUS_MODEL:
        if state.model_preview is not None:
            api = state.current_api() if CONFIG.get("apis") else None
            models = (api or {}).get("models", [])
            if models:
                state.model_idx = max(0, min(state.model_preview, len(models) - 1))
                state.model_preview = state.model_idx

    elif f == FOCUS_THINK:
        if state.reasoning_preview is not None and state.reasoning_preview in THINK_LEVELS:
            state.reasoning_effort = state.reasoning_preview
            state.reasoning_preview = state.reasoning_effort

    elif f == FOCUS_NAV:
        blocks = state.display_blocks()
        if blocks:
            width = term_size()[0]
            target = 0
            for i, blk in enumerate(blocks):
                if i == state.nav_idx:
                    break
                materialize_block(blk, width)
                target += len(blk["q_lines"])
                if blk.get("done") and blk.get("think_lines"):
                    if blk.get("think_collapsed"):
                        target += 1
                    else:
                        target += len(blk["think_lines"]) + 1
                target += len(blk.get("ans_lines") or []) + 1
            state.follow_output = False
            state.viewport_offset = target

    elif f == FOCUS_HIST:
        if state.history_files:
            idx = min(state.history_idx, len(state.history_files) - 1)
            path = state.history_files[idx]
            if path == state.current_chat_path:
                exit_view_mode()
            else:
                load_history_to_view(path)

    event.app.invalidate()


@kb.add("c-j")
def _(event):
    if in_input():
        state.input.insert("\n")
        event.app.invalidate()


@kb.add("backspace")
def _(event):
    if in_input():
        state.input.backspace()
        event.app.invalidate()


@kb.add("delete")
def _(event):
    if in_input():
        state.input.delete()
        event.app.invalidate()


@kb.add("home")
def _(event):
    if in_input():
        state.input.home()
        event.app.invalidate()


@kb.add("end")
def _(event):
    if in_input():
        state.input.end()
        event.app.invalidate()


@kb.add("c-c")
def _(event):
    try:
        save_current_chat()
        delete_current_if_empty()
    except Exception:
        pass
    event.app.exit()


@kb.add("c-r")
def _(event):
    global CONFIG
    try:
        new_cfg = load_config()
    except Exception as e:
        state.notice = "配置读取失败: %s" % e
        event.app.invalidate()
        return

    err = validate_config(new_cfg)
    if err:
        state.notice = "配置错误: " + err
        event.app.invalidate()
        return

    CONFIG = new_cfg
    _title_cache.clear()
    revalidate_state_after_reload()
    state.notice = ""
    event.app.invalidate()


@kb.add("escape")
def _(event):
    if state.streaming:
        state.abort_event.set()
        event.app.invalidate()


@kb.add(Keys.Any)
def _(event):
    if not in_input():
        return
    data = event.data
    if not data:
        return
    if all(c.isprintable() for c in data):
        state.input.insert(data)
        event.app.invalidate()


# ═══════════════════════════════════════════════════════════════
# 样式定义
# ═══════════════════════════════════════════════════════════════

STYLE = Style.from_dict({
    # ── 输出区 ──
    "output-focused": "bg:#1a1a2e",
    "output-blur":    "bg:#000000",
    "bar":            "#00afff bold",

    # 输出内容样式
    "q":     "#00afff bold",
    "ans":   "#ffffff",
    "think": "#888888 italic",
    "hint":  "#666666",

    # ── 输入区 ──
    "prompt-focused": "#00ff00 bold",
    "prompt-blur":    "#666666",
    "input-focused":  "#ffffff",
    "input-blur":     "#888888",
    "input-disabled": "#666666",
    "cursor-block":   "reverse #00ff00 bold",

    # ── 底部状态栏 ──
    "status":               "bg:#333333 #cccccc",
    "status-active":        "bg:#005f87 #ffffff bold",
    "status-effective":     "#00afff bold",
    "status-dim":           "#666666",
    "status-bracket-blue":  "bg:#005f87 #ffffff bold",
    "status-bracket-yellow":"bg:#ffaf00 #000000 bold",
    "status-token":         "#00ff88 bold",
    "status-warn":          "bg:#870000 #ffffff bold",
})


# ═══════════════════════════════════════════════════════════════
# 布局与应用
# ═══════════════════════════════════════════════════════════════

def build_layout():
    output_win = Window(
        content=FormattedTextControl(get_output_text),
        wrap_lines=False,
        height=Dimension(weight=1),
    )
    input_win = Window(
        content=FormattedTextControl(get_input_text),
        height=Dimension.exact(2),
    )
    status_win = Window(
        content=FormattedTextControl(get_status_text),
        height=Dimension.exact(1),
    )
    root = HSplit([output_win, input_win, status_win])
    return Layout(root)


# ═══════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════

async def main_async():
    new_chat()
    cleanup_empty_chats(keep_path=state.current_chat_path)
    refresh_history()

    app = Application(
        layout=build_layout(),
        key_bindings=kb,
        style=STYLE,
        full_screen=True,
        mouse_support=False,
    )
    await app.run_async()


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
