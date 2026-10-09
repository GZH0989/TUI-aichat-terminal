# TUI-aichat-terminal — 终端 AI 对话程序

[![Repo](https://img.shields.io/badge/repo-TUI--aichat--terminal-blue)](https://github.com/GZH0989/TUI-aichat-terminal)
[![Python](https://img.shields.io/badge/python-3.11%2B%20%7C%20standalone-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()
[![AI Generated](https://img.shields.io/badge/AI%20Generated-DeepSeek-ff69b4.svg)]()
[![License](https://img.shields.io/badge/license-MIT--NoWarranty-yellow.svg)]()

> 在终端里运行的极简 AI 对话程序。纯键盘操作，支持流式思考、多 API 热切换、历史对话浏览。
>
> **⚠️ 本项目的全部代码与文件均由 DeepSeek 生成，作者仅做整理与发布。使用风险自负，详见下方免责声明。**

---

## 目录

- [简介](#简介)
- [特性](#特性)
- [环境要求](#环境要求)
- [安装策略](#安装策略)
- [快速开始](#快速开始)
- [使用说明](#使用说明)
- [配置](#配置)
- [数据存储](#数据存储)
- [修复与升级](#修复与升级)
- [常见问题](#常见问题)
- [免责声明](#免责声明)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 简介

**TUI-aichat-terminal** 是一个在命令行里运行的 AI 对话程序。所有操作通过键盘完成，不依赖图形界面。支持 **Linux**、**macOS**、**Windows 10/11**。

本项目使用 OpenAI 兼容的 Chat Completions API（SSE 流式），默认适配 DeepSeek，也可自行添加任何兼容网关。

安装方案提供两条路径：**基于系统 Python 的本地 venv**（约 30 MB），或**下载一份独立的 Python 运行时到 runtime/**（约 150 MB）。脚本会根据你的环境自动选择，不污染系统环境，整个文件夹可以随意移动。

---

## 特性

- **纯键盘操作**：`↑↓` 切焦点、`←→` 操作、`Enter` 确认
- **思考过程可视**：实时流式显示，可随时折叠/展开
- **思考强度四档**：关 / 低 / 高 / 最高，运行时热切换
- **多 API 热切换**：配置多个 API，运行时切换，无需重启
- **历史对话浏览**：每次问答自动保存，可随时翻阅
- **Token 用量显示**：状态栏实时显示本次请求消耗
- **长时间思考不断线**：大读取超时 + TCP keepalive
- **双安装路径**：有合适的系统 Python 就用 venv，否则自动下载独立运行时
- **环境健康测试**：安装时自动检测系统 Python 是否可用（识别沙箱版 / 精简版）
- **完全沙盒化**：所有内容都在程序文件夹内，不污染系统
- **可移动**：整个文件夹可以任意移动，无需重新配置

---

## 环境要求

| 项目        | 要求                                                     |
| ----------- | -------------------------------------------------------- |
| 操作系统    | Linux / macOS / Windows 10 或 11                         |
| 系统 Python | **3.8+**（用于运行安装脚本）；**3.11+** 才能走 venv 方案 |
| 终端尺寸    | 最小 6 行 × 80 列                                        |
| 网络        | 能访问国内镜像站（中科大、清华等）                       |
| 磁盘空间    | 约 **30 MB**（venv 方案）或 **150 MB**（runtime 方案）   |

**关于 Python 版本**：

- 主程序 `import tomllib`，这是 Python **3.11** 才进标准库的模块，因此主程序本身要求 Python ≥ 3.11。
- 安装脚本本身只用到标准库的 `urllib` / `tarfile` / `subprocess`，系统 Python ≥ 3.8 就能跑。
- 如果系统 Python < 3.11，安装脚本会直接询问是否下载独立的 Python 3.12 运行时。
- 如果系统 Python ≥ 3.11，安装脚本会先做一次环境健康测试，通过后优先用系统 Python 创建 `venv/`；失败时自动回退，询问是否下载独立运行时。

**Windows 提示**：推荐使用 **Windows Terminal**（微软商店免费），对 Unicode 和宽字符支持更好。传统 cmd 也能用，但中文渲染可能有瑕疵。

**⚠️ 不要双击 `ai_terminal.py`**：Windows 会把 `.py` 文件关联到某个不知名的 Python 解释器（可能是 Microsoft Store 沙箱版），导致程序运行失败。**始终通过 `ai-term.bat` 启动。**

---

## 安装策略

安装脚本会根据你的环境自动选择方案，具体如下：

| 系统 Python 版本             | 默认行为                       | 存储占用        |
| ---------------------------- | ------------------------------ | --------------- |
| `< 3.11`                     | 提示必须下载独立运行时         | runtime ~150 MB |
| `>= 3.11` 且环境健康测试通过 | 优先用系统 Python 创建 `venv/` | venv ~30 MB     |
| `>= 3.11` 但环境健康测试失败 | 提示下载独立运行时             | runtime ~150 MB |

**环境健康测试是什么？**

当系统 Python ≥ 3.11 时，安装脚本会先在临时目录里试装一个小包（`wcwidth`），然后尝试导入它。这一步可以识别出：

- Microsoft Store 沙箱版 Python（`WindowsApps\` 下的那种）
- pythoncore 精简版 Python（`AppData\Local\Python\pythoncore-*\` 下的那种）
- pip 配置错误、网络异常、权限问题

测试通过才走 venv 方案。测试失败会打印具体原因，然后询问是否改用独立环境。整个测试过程只需 1~3 秒，临时目录无论成败都会被清理。

**为什么高版本 Python 反而可能失败？**

Python 生态整体向后兼容，低版本库能在高版本 Python 上运行。但 Python 大版本刚发布时，一些带 C 扩展的库（如 `aiohttp` 依赖的 `multidict`、`yarl`）可能还没发布适配新版本的预编译 wheel，此时 `pip` 会尝试源码编译；如果本地没有 C 编译工具链，安装就会失败。脚本检测到这种情况后会自动回退到独立运行时方案。

**为什么有两套方案？**

- **venv 方案**：复用系统 Python，只装依赖，体积小（约 30 MB）。适合系统 Python 干净、版本合适的环境。
- **runtime 方案**：下载一份完整的 Python 运行时（约 150 MB），完全独立于系统。适合系统 Python 太老、被污染、或是沙箱版的环境。

两套方案生成的目录（`venv/` 或 `runtime/`）**只会存在一个**，启动器会自动检测。

---

## 快速开始

只需要一个文件：**`一键安装修复脚本.py`**。

### 第一步：获取脚本

从本仓库下载 `一键安装修复脚本.py`，或者直接克隆整个仓库：

```bash
git clone https://github.com/GZH0989/TUI-aichat-terminal.git
cd TUI-aichat-terminal
```

### 第二步：运行安装脚本

确保系统已经装了 **Python 3.8 或更高**（用来跑安装脚本本身），然后在命令行里：

```bash
python 一键安装修复脚本.py
```

Windows 用户可以在文件所在目录的地址栏输入 `cmd` 回车，然后敲上面的命令。

脚本会按以下顺序交互：

1. **检查是否已有可用环境**（`runtime/` 或 `venv/` 中已有完整依赖）——有就直接释放文件和启动器。
2. **检查系统 Python 版本**：
   - `< 3.11`：提示必须下载独立运行时（`[y/N]`，默认退出）。
   - `>= 3.11`：询问是否开始环境健康测试（`[Y/n]`，默认继续）。
3. **环境健康测试**（仅 `>= 3.11` 时）：
   - 通过 → 询问是否用系统 Python 创建 `venv/`（`[Y/n]`，默认继续）。
   - 失败 → 打印原因，询问是否下载独立运行时（`[y/N]`，默认退出）。
4. **安装**：根据你的选择走 `venv/` 或 `runtime/` 方案。
5. 释放 `ai_terminal.py`、本手册、启动器和 `chat/` 目录。

**整个过程不污染系统环境**，所有东西都在脚本所在文件夹里。

### 第三步：启动

**Linux / macOS：**

```bash
./ai-term
```

**Windows：**

双击 `ai-term.bat`。

启动器会自动检测 `runtime/` 或 `venv/` 中可用的 Python，优先用 `runtime/`。

### 第四步：填入 API key

首次启动会提示“未配置 API key”。这时候：

1. 用任意编辑器打开同目录下的 `config.toml`
2. 找到 `api_key = ""`，改成 `api_key = "sk-你的真实密钥"`
3. 保存
4. 回到程序窗口，按 **`Ctrl+R`** 热重载

可以开始提问了。

---

## 使用说明

### 界面结构

```
┌─────────────────────────────────────────────┐
│                                             │
│              输出区（对话内容）             │
│              高度 = 窗口高度 - 3            │
│                                             │
├─────────────────────────────────────────────┤
│  >>> 输入框第 1 行                          │  ← 输入框（2 行）
│      输入框第 2 行                          │
├─────────────────────────────────────────────┤
│  API:model 思考:档位 [导航] [历史]  ↑↓ ...  │  ← 状态栏（1 行）
└─────────────────────────────────────────────┘
```

### 焦点循环

按 `↑` 或 `↓` 在 7 个控件之间循环：

```
输出区 → 输入框 → API → Model → 思考 → 问题导航 → 历史对话 → 输出区
```

当前焦点的视觉提示：

- **输出区**：左列显示亮色竖条 `▌`，背景变暗蓝
- **输入框**：提示符 `>>>` 变亮绿，光标是反色方块
- **底部控件**：占满整行

### 键位总览

| 按键                   | 作用                                      |
| ---------------------- | ----------------------------------------- |
| `↑` / `↓`              | 切换焦点（在控件之间循环）                |
| `←` / `→`              | 当前控件内的水平操作                      |
| `Enter`                | 确认/发送（输入框里是发送，控件里是确认） |
| `Ctrl+Enter`           | 输入框内换行                              |
| `Esc`                  | 中断当前流式请求                          |
| `Ctrl+R`               | 热重载 `config.toml`                      |
| `Ctrl+C`               | 保存并退出                                |
| `Backspace` / `Delete` | 输入框内删字符                            |
| `Home` / `End`         | 输入框内跳首尾                            |

### 各焦点的具体行为

**输出区**

- `←` / `→`：向上 / 向下滚动一行
- `Enter`：折叠 / 展开当前选中问答的思考过程

**输入框**

- `←` / `→`：左右移动光标
- `Enter`：发送
- `Ctrl+Enter`：插入换行（支持多行输入）

**API / Model / 思考**

- `←` / `→`：预览切换值（**不立即生效**）
- `Enter`：确认切换

预览期间：

- **蓝底高亮** = 光标位置就是当前生效值
- **黄底高亮** = 光标位置是待确认的新值
- 按 `↑` / `↓` 离开焦点会**丢弃未确认的预览**

**问题导航**

- `←` / `→`：上一个 / 下一个问答
- `Enter`：把输出区跳转到该问答的位置

**历史对话**

- `←` / `→`：上一个 / 下一个历史对话文件
- `Enter`：加载该对话到输出区（进入查看模式）

当前对话在列表里带 `<当前>` 后缀。选中当前对话按 `Enter` 会退出查看模式，回到当前会话。查看模式下输入框禁用。

### 思考强度档位

| 档位   | 显示 | 说明               |
| ------ | ---- | ------------------ |
| `none` | 关   | 完全不思考         |
| `low`  | 低   | 轻量推理           |
| `high` | 高   | 默认，标准推理     |
| `max`  | 最高 | 深度推理，最慢最贵 |

### 思考过程折叠

每条回答如果有思考内容，第一行会显示：

```
▶ 思考过程（N 行，Enter 展开）
```

把焦点切到输出区（`↑↓`），按 `Enter` 展开，再按 `Enter` 折叠。

### 中断与退出

- **流式中途想停**：按 `Esc`。已生成的内容会保留，对话仍会保存。
- **退出程序**：按 `Ctrl+C`。当前对话会自动保存，空对话会删除空文件。

---

## 配置

配置文件：`config.toml`（与程序同目录）
修改后按 **`Ctrl+R`** 热重载，不用重启程序。

### API 配置

`config.toml` 里可以有多个 `[[apis]]`，程序运行时通过底部状态栏切换。

每一项支持以下字段：

| 字段          | 必填 | 说明                                     |
| ------------- | ---- | ---------------------------------------- |
| `name`        | ✅    | API 的显示名（自定义，用于运行时识别）   |
| `base_url`    | ✅    | OpenAI 兼容的 API 端点（末尾不要带 `/`） |
| `api_key`     | ❌    | 直接写明文密钥（方便，但不安全）         |
| `api_key_env` | ❌    | 从环境变量读密钥（更安全，推荐）         |
| `models`      | ✅    | 该 API 下可用的模型列表                  |

`api_key` 和 `api_key_env` 二选一，都填时 `api_key` 优先。

**通用模板**：

```toml
[[apis]]
name = "自定义名称"
base_url = "https://your-api-endpoint.com/v1"
api_key = ""
api_key_env = "YOUR_API_KEY_ENV"
models = ["模型1", "模型2"]
```

**具体示例（DeepSeek）**：

```toml
[[apis]]
name = "deepseek"
base_url = "https://api.deepseek.com/v1"
api_key = ""
api_key_env = "DEEPSEEK_API_KEY"
models = ["deepseek-reasoner", "deepseek-chat"]
```

**具体示例（Moonshot / Kimi）**：

```toml
[[apis]]
name = "moonshot"
base_url = "https://api.moonshot.cn/v1"
api_key = "sk-你的真实密钥"
models = ["moonshot-v1-128k", "moonshot-v1-32k"]
```

**具体示例（OpenAI）**：

```toml
[[apis]]
name = "openai"
base_url = "https://api.openai.com/v1"
api_key = ""
api_key_env = "OPENAI_API_KEY"
models = ["gpt-4o", "gpt-4o-mini"]
```

只要 API 兼容 OpenAI 的 Chat Completions 协议（绝大多数国内网关都兼容），都可以通过 `[[apis]]` 加进来。

### 常用配置项

| 字段                    | 说明             | 建议                    |
| ----------------------- | ---------------- | ----------------------- |
| `reasoning_effort`      | 启动时思考强度   | `"high"`                |
| `max_tokens`            | 历史上下文预算   | `32000`                 |
| `passthrough_reasoning` | 是否回传思考过程 | `false`（直连官方 API） |
| `auto_summarize`        | 超长对话自动摘要 | `false`（先关着）       |
| `sock_read_timeout`     | 读取超时（秒）   | `600`                   |

### 网络配置

网络相关配置全部放在 `[network]` 段：

```toml
[network]
sock_read_timeout = 600
connect_timeout = 30
tcp_keepidle = 30
tcp_keepintvl = 10
tcp_keepcnt = 3
```

如果模型思考时间很长，可以把 `sock_read_timeout` 调大，例如 `1200`。

---

## 数据存储

### 目录结构

```
<你放脚本的目录>/
├── 一键安装修复脚本.py     # 安装脚本（可保留，也可删）
├── ai_terminal.py          # 主程序（自动生成）
├── README.md               # 本手册（自动生成）
├── config.toml             # 配置（含 API key，自动生成）
├── ai-term / ai-term.bat   # 启动器（自动生成）
├── runtime/                # 独立 Python 运行时（约 150 MB，下载方案）
├── venv/                   # 本地虚拟环境（约 30 MB，系统 Python 方案）
└── chat/                   # 对话记录
```

`runtime/` 和 `venv/` **只会存在一个**，具体是哪一个取决于安装时选择的方案。启动器会自动检测并使用存在的那个。

### 对话文件格式

每个对话是一个独立 JSON 文件，命名格式 `YYYY-MM-DD_HH-MM-SS_xxx.json`：

```json
{
  "created": "2026-10-07T14:30:00",
  "updated": "2026-10-07T14:35:12",
  "api": "deepseek",
  "model": "deepseek-reasoner",
  "messages": [
    {"role": "user", "content": "..."},
    {
      "role": "assistant",
      "content": "...",
      "reasoning_content": "..."
    }
  ]
}
```

### 备份

直接复制 `chat/` 目录即可，所有历史都在里面。

### 迁移

**整个文件夹可以随便移动**。但如果跨平台（例如从 Linux 拷到 Windows），需要在**新机器上重新运行安装脚本**，因为 `runtime/` 或 `venv/` 都是平台相关的，必须重建。`config.toml` 和 `chat/` 会保留。

### 清理

删除不想要的对话，直接删 `chat/` 下对应的 JSON 文件。程序在启动时会自动清理符合命名规则的空对话文件。

---

## 修复与升级

### 修复环境

如果运行出错（比如依赖损坏、Python 运行时丢失），重新运行一次安装脚本：

```bash
python 一键安装修复脚本.py
```

脚本会先检查是否已有可用环境，能修复就修复，不能则重新安装。**不会覆盖 `config.toml` 和 `chat/`。**

### 升级主程序

拿到新版 `一键安装修复脚本.py` 后：

1. 用新版替换旧版
2. 运行它
3. 它会用新版主程序覆盖 `ai_terminal.py`，其他文件保留

如果新版引入了新配置项，程序会在读取配置时用默认值兜底，不会崩。

### 切换安装方案

想从 `venv/` 切到 `runtime/`（或者反过来）：

1. 删除想放弃的那个目录（`venv/` 或 `runtime/`）
2. 重新运行安装脚本，在询问时选择另一种方案

### 从 venv 换到 runtime（节省排查时间）

如果 venv 方案程序能跑，但偶发依赖问题，可以直接删掉 `venv/` 目录再重跑安装脚本，选择下载独立运行时。这种方式不依赖系统 Python，最稳定。

---

## 常见问题

### Q：我用 Python 3.14 跑安装脚本，aiohttp 装不上

**先决条件**：Python 3.14 刚发布时，`aiohttp` 及其 C 扩展依赖（`multidict`、`yarl`、`frozenlist`）的 `cp314` 预编译 wheel 可能还没同步到国内镜像。现在通常已经就绪。

**如果确实装不上**，安装脚本的环境健康测试会失败，打印原因后会询问是否下载独立环境，直接回车（默认 Y）即可。脚本会下载一份 Python 3.12 运行时，在独立环境里安装依赖，不受系统 Python 版本影响。

### Q：安装脚本问我要不要测试环境 / 下载独立环境，我该选哪个？

- **系统 Python ≥ 3.11 且干净**：环境测试通过 → 选 Y 用 venv（省空间，约 30 MB）。
- **系统 Python 是 Microsoft Store 版 / pythoncore 版**：环境测试会失败 → 选 Y 下载独立环境（约 150 MB）。
- **系统 Python < 3.11**：脚本直接要求下载独立环境。

**如果磁盘空间充裕，追求稳定，任何时候选下载独立环境都是对的。**

### Q：安装完后文件夹占多少空间？

- **venv 方案**：约 **30 MB**（依赖 + 少量元数据，Python 本体由系统提供）
- **runtime 方案**：约 **150 MB**（完整 Python 运行时 + 依赖）

`chat/` 目录会随对话增长，每个 JSON 文件几十 KB 到几 MB 不等。长期使用后建议定期备份并清理。

### Q：为什么 Windows 上双击 `ai-term.bat` 一闪而过？

如果程序报错，窗口会自动关闭看不到信息。有两种办法：

1. 在 cmd 里手动运行：

   ```bat
   cd /d 你的目录
   ai-term.bat
   ```

   程序退出后 cmd 窗口保留，错误信息能看清。

2. 最新版的 `ai-term.bat` 已经加了 `if errorlevel 1 pause`，程序异常退出时会自动暂停。如果还是闪退，说明启动器根本没运行到那一步（比如找不到 Python 环境），这种情况启动器会自己 pause 一次。

### Q：为什么双击 `ai_terminal.py`有时会报错或闪退？

Windows 会把 `.py` 文件关联到系统里某个 Python 解释器（可能是 Microsoft Store 沙箱版），那个解释器可能缺少依赖、无法联网、或者根本不是你安装时用的那个。**始终通过 `ai-term.bat` 启动**，它用的是项目里装好的 Python 环境。

### Q：运行脚本时报 `No module named 'venv'`（Linux）

这是 **venv 方案**下的依赖问题。系统 Python 缺少 `venv` 模块。安装：

```bash
sudo apt install python3-venv
```

（Ubuntu/Debian 默认不装 `python3-venv`，需要单独安装。）其他发行版：

```bash
# Fedora / RHEL
sudo dnf install python3-venv

# Arch
sudo pacman -S python
```

如果不想装 venv，也可以重新运行安装脚本，选择下载独立运行时。

### Q：运行脚本报 `No module named 'tomllib'`

系统 Python 太老（< 3.11）。但**不影响**安装脚本本身——脚本只用标准库的 `urllib` / `tarfile` / `subprocess`，不需要 `tomllib`。这个报错应该来自主程序，主程序运行在独立 Python 3.12 或本地 venv 上。如果确认是主程序报的，重新运行安装脚本并选择下载独立运行时。

### Q：下载 Python 时报错 `所有镜像均下载失败`

可能原因：

- 网络不通
- 防火墙拦截了 github 相关域名（镜像站也是代理 github）

尝试：

- 换个网络
- 手动去 [github 原版](https://github.com/astral-sh/python-build-standalone/releases) 下载对应平台的 `cpython-3.12.7+20241016-*-install_only.tar.gz`，解压到 `runtime/python/` 目录里
- 或者把网络错误信息发给其他 AI，让它帮忙解决

### Q：安装脚本能运行，但 `./ai-term` 报错 `permission denied`（Linux）

给启动器加执行权限：

```bash
chmod +x ai-term
```

或者直接 `bash ai-term`。

### Q：API 报错 `未配置 API key`

编辑 `config.toml`，把 `api_key = ""` 改成真实密钥。保存后按 **`Ctrl+R`** 热重载。

### Q：思考很久后报 `网络错误`

打开 `config.toml`，找到：

```toml
[network]
sock_read_timeout = 600
```

把它改成更大的值（比如 `1200`），保存，`Ctrl+R` 重载。

如果仍然频繁发生，可能是公司网关强制断开长连接。这种情况无解，只能换网络。

### Q：思考内容里有奇怪的蓝色字符

那是模型输出里混入的 ANSI 转义序列。程序已经过滤掉控制字符，如果还看到，说明是其他可见的 Unicode 字符，不是 bug。

### Q：光标看不到

输入框聚焦时，光标是一个**反色方块**（不是终端自带光标）。如果看不到：

- **Linux**：`tput sgr0` 重置终端属性
- **Windows**：换用 Windows Terminal

### Q：`Ctrl+Enter` 不换行

部分终端把 `Ctrl+Enter` 识别为 `Enter`。替代方案：

- 用单行输入
- 或者换终端（Windows Terminal 支持自定义键绑定）

### Q：如何完全卸载

删掉整个文件夹即可。系统层面没有任何残留，环境变量、注册表都没动。

---

## 免责声明

> **请在使用前仔细阅读以下内容。**

1. **本项目的全部代码与文件均由 DeepSeek 生成**，作者仅进行了整理、打包和发布。作者不是原始开发者，也不对代码的原创性、正确性、安全性、稳定性做任何保证。
2. 本项目按“**原样**”提供，不提供任何明示或暗示的担保，包括但不限于对适销性、特定用途适用性及非侵权的保证。
3. 使用本项目产生的任何后果——包括但不限于 **API 费用、数据丢失、对话内容泄露、法律风险、设备损坏**——由使用者自行承担。作者不承担任何责任。
4. 本项目会调用第三方 AI API，请遵守对应服务商的条款。API key 由使用者自行保管，作者不会收集、存储或上传任何密钥或对话内容。
5. 如果遇到问题，你可以：
   - 自行阅读代码并修改；
   - 向其他开发者或社区求助；
   - 向其他 AI 助手提问；
   - 在本仓库提交 Issue，但作者**不保证**能及时回复或修复。
6. 下载并使用本项目，即表示你已理解并同意上述条款。

---

## 贡献

欢迎在本仓库提交 Issue 或 Pull Request：
<https://github.com/GZH0989/TUI-aichat-terminal>

但请注意：

- 作者可能无法及时回复。
- 代码由 AI 生成，可能存在未发现的问题，欢迎指出。
- 提交 PR 前请自行测试。

---

## 许可证

本项目采用 **MIT 许可证（无担保）**。你可以自由使用、修改、分发，风险自负。

---

## 致谢

- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — 终端 UI 框架
- [aiohttp](https://github.com/aio-libs/aiohttp) — 异步 HTTP 客户端
- [python-build-standalone](https://github.com/astral-sh/python-build-standalone) — 独立 Python 运行时
- [DeepSeek](https://www.deepseek.com/) — 本项目的全部代码与文件由 DeepSeek 生成
