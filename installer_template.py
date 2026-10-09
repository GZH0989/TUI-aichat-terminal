#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 终端 一键安装 / 修复脚本（Windows / Linux / macOS 通用）
============================================================

用法:
    python 一键安装修复脚本.py

安装流程:
    0. 检查是否已有可用环境（runtime/ 或 venv/）
    1. (a) 检查系统 Python 版本
    2. (d) 测试 pip 健康度（临时目录装 wcwidth 再导入）
    3. (b) 下载独立 Python 运行时（可选）
    4. (c) 用系统 Python 创建本地 venv（可选）
    5. 释放主程序 / README / 启动器

pip 源策略:
    所有 pip 命令先试默认源；失败自动切清华镜像重试一次。

生成的文件:
    runtime/           独立 Python 运行环境（下载方案）
    venv/              基于系统 Python 的虚拟环境（系统方案）
    ai_terminal.py     主程序
    README.md          说明文档
    ai-term            Linux/macOS 启动器
    ai-term.bat        Windows 启动器
    config.toml        首次运行主程序时自动生成
    chat/              对话记录目录
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# 版本要求
# ═══════════════════════════════════════════════════════════════

MIN_PY_FOR_MAIN = (3, 11)
MIN_PY_FOR_SELF = (3, 8)

if sys.version_info < MIN_PY_FOR_SELF:
    sys.stderr.write(
        "\n[错误] 本脚本需要 Python %d.%d 或更高版本。\n"
        "       当前版本: %s\n"
        "       请从 https://www.python.org/downloads/ 安装新版。\n\n"
        % (MIN_PY_FOR_SELF[0], MIN_PY_FOR_SELF[1], sys.version.split()[0])
    )
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 路径与常量
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR / "runtime"
VENV_DIR = SCRIPT_DIR / "venv"

PYTHON_VERSION = "3.12.7"
PBS_RELEASE_TAG = "20241016"

MIRRORS = [
    "https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/",
    "https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone/",
    "https://mirror.lzu.edu.cn/github-release/astral-sh/python-build-standalone/",
    "https://cnb.cool/astral-sh/python-build-standalone/-/releases/download/",
    "https://github.com/astral-sh/python-build-standalone/releases/download/",
]

PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
PYPI_TRUSTED_HOST = "pypi.tuna.tsinghua.edu.cn"

DEPENDENCIES = ["aiohttp", "prompt_toolkit"]
HEALTH_TEST_PKG = "wcwidth"

# ═══════════════════════════════════════════════════════════════
# 内嵌文件（由 fill.py 自动替换）
# ═══════════════════════════════════════════════════════════════

AI_TERMINAL_PY = r'''@@AI_TERMINAL_PY@@'''

README_MD = r'''@@README_MD@@'''

# ═══════════════════════════════════════════════════════════════
# 输出工具
# ═══════════════════════════════════════════════════════════════

def _c(code, text):
    if not sys.stdout.isatty():
        return text
    if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
        return text
    return "\033[%sm%s\033[0m" % (code, text)


def info(msg):  print("%s %s" % (_c("36", "[INFO]"), msg))
def ok(msg):    print("%s %s" % (_c("32", "[ OK ]"), msg))
def warn(msg):  print("%s %s" % (_c("33", "[WARN]"), msg))
def error(msg): print("%s %s" % (_c("31", "[FAIL]"), msg))


def banner(text):
    print()
    print("=" * 60)
    print("  " + text)
    print("=" * 60)
    print()


# ═══════════════════════════════════════════════════════════════
# 平台检测
# ═══════════════════════════════════════════════════════════════

def is_windows():
    return platform.system() == "Windows"


def get_platform_info():
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        if machine in ("amd64", "x86_64"):
            return "x86_64-pc-windows-msvc"
        elif machine in ("arm64", "aarch64"):
            return "aarch64-pc-windows-msvc"
        raise RuntimeError("不支持的 Windows 架构: %s" % machine)

    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "x86_64-unknown-linux-gnu"
        elif machine in ("aarch64", "arm64"):
            return "aarch64-unknown-linux-gnu"
        raise RuntimeError("不支持的 Linux 架构: %s" % machine)

    if system == "Darwin":
        if machine in ("x86_64", "amd64"):
            return "x86_64-apple-darwin"
        elif machine in ("aarch64", "arm64"):
            return "aarch64-apple-darwin"
        raise RuntimeError("不支持的 macOS 架构: %s" % machine)

    raise RuntimeError("不支持的操作系统: %s" % system)


# ═══════════════════════════════════════════════════════════════
# 交互工具
# ═══════════════════════════════════════════════════════════════

def ask_three_way(prompt, default):
    """
    三态询问。返回 True / False / None。
        True  = 用户选 yes（或回车采用默认且默认是 True）
        False = 用户选 no（或回车采用默认且默认是 False）
        None  = 用户输入了其他内容（调用者通常应退出）
    非交互式环境下直接返回默认值。
    """
    hint = "[Y/n]" if default else "[y/N]"
    try:
        ans = input("%s %s " % (prompt, hint)).strip().lower()
    except EOFError:
        print()
        return default
    except KeyboardInterrupt:
        print()
        sys.exit(1)
    if not ans:
        return default
    if ans in ("y", "yes"):
        return True
    if ans in ("n", "no"):
        return False
    return None


# ═══════════════════════════════════════════════════════════════
# Python 路径
# ═══════════════════════════════════════════════════════════════

def runtime_python():
    if is_windows():
        return RUNTIME_DIR / "python" / "python.exe"
    return RUNTIME_DIR / "python" / "bin" / "python3"


def venv_python():
    if is_windows():
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def check_python_has_deps(py_path):
    if not py_path.exists():
        return False
    try:
        r = subprocess.run(
            [str(py_path), "-c",
             "import sys, aiohttp, prompt_toolkit, tomllib; "
             "assert sys.version_info >= (3, 11)"],
            capture_output=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def find_usable_env():
    rp = runtime_python()
    if rp.exists() and check_python_has_deps(rp):
        return rp, "runtime"
    vp = venv_python()
    if vp.exists() and check_python_has_deps(vp):
        return vp, "venv"
    return None, None


# ═══════════════════════════════════════════════════════════════
# pip 封装：默认源 → 清华源 自动回退
# ═══════════════════════════════════════════════════════════════

def _pip_run(py_path, pip_args, timeout=300):
    """
    执行一次 pip 命令。返回 (ok, stderr_tail)。
    不指定 index-url，让 pip 使用默认源。
    """
    cmd = [str(py_path), "-m", "pip"] + pip_args + [
        "--no-warn-script-location",
        "--quiet",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return True, ""
        tail = "\n".join((r.stderr or "").strip().splitlines()[-3:])
        return False, tail
    except subprocess.TimeoutExpired:
        return False, "pip 命令超时"
    except Exception as e:
        return False, "pip 命令异常: %s" % e


def _pip_run_with_mirror(py_path, pip_args, timeout=300):
    """同上，但显式指定清华源。"""
    cmd = [str(py_path), "-m", "pip"] + pip_args + [
        "-i", PYPI_MIRROR,
        "--trusted-host", PYPI_TRUSTED_HOST,
        "--no-warn-script-location",
        "--quiet",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return True, ""
        tail = "\n".join((r.stderr or "").strip().splitlines()[-3:])
        return False, tail
    except subprocess.TimeoutExpired:
        return False, "pip 命令超时"
    except Exception as e:
        return False, "pip 命令异常: %s" % e


def pip_install_with_fallback(py_path, packages, extra_args=None, timeout=300):
    """
    先默认源，失败再清华源。返回 (ok, last_err)。
    """
    extra_args = extra_args or []
    pip_args = ["install", "--upgrade"] + list(packages) + list(extra_args)

    ok1, err1 = _pip_run(py_path, pip_args, timeout=timeout)
    if ok1:
        return True, ""

    info("默认源失败，尝试清华镜像 ...")
    ok2, err2 = _pip_run_with_mirror(py_path, pip_args, timeout=timeout)
    if ok2:
        return True, ""

    # 两个都失败，返回信息更完整的那个（一般两个差不多）
    err = err1 if err1 else err2
    return False, err


# ═══════════════════════════════════════════════════════════════
# 依赖安装
# ═══════════════════════════════════════════════════════════════

def install_deps(py_path):
    if not py_path.exists():
        error("Python 不存在: %s" % py_path)
        return False

    info("升级 pip ...")
    up_ok, _ = pip_install_with_fallback(
        py_path, [], extra_args=["pip"], timeout=180
    )
    # 上面的调用不太对——pip 升级有专门语法，改一下：
    # 直接升级 pip 包
    up_cmd_args = ["install", "--upgrade", "pip"]
    ok1, _ = _pip_run(py_path, up_cmd_args, timeout=180)
    if not ok1:
        ok2, _ = _pip_run_with_mirror(py_path, up_cmd_args, timeout=180)
        if not ok2:
            warn("pip 升级失败（不致命，继续）")

    info("安装依赖: %s" % ", ".join(DEPENDENCIES))
    ok_inst, err = pip_install_with_fallback(py_path, DEPENDENCIES, timeout=600)
    if not ok_inst:
        error("依赖安装失败: %s" % err)
        return False

    if not check_python_has_deps(py_path):
        error("依赖安装后验证失败")
        return False

    ok("依赖安装完成")
    return True


# ═══════════════════════════════════════════════════════════════
# 环境健康测试（d）
# ═══════════════════════════════════════════════════════════════

def _pip_target_install(py_path, pkg, target_dir, use_mirror, timeout=180):
    args = [
        str(py_path), "-m", "pip", "install", pkg,
        "--target", str(target_dir),
        "--no-warn-script-location",
        "--quiet",
    ]
    if use_mirror:
        args += ["-i", PYPI_MIRROR, "--trusted-host", PYPI_TRUSTED_HOST]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return True, ""
        tail = "\n".join((r.stderr or "").strip().splitlines()[-3:])
        return False, tail
    except subprocess.TimeoutExpired:
        return False, "pip 命令超时"
    except Exception as e:
        return False, "pip 命令异常: %s" % e


def test_pip_health():
    """
    在当前 Python 上测试 pip 健康度：
      1. 装 wcwidth 到临时目录（先默认源，失败切清华）
      2. 用子进程把该目录加入 sys.path 后 import wcwidth
    无论成败，临时目录都会被清理。
    返回 True 表示健康。
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="ai_term_test_"))
    target_dir = tmp_dir / "target"
    target_dir.mkdir()

    try:
        info("测试 1/2：安装 %s 到临时目录 ..." % HEALTH_TEST_PKG)
        ok_install, err = _pip_target_install(
            sys.executable, HEALTH_TEST_PKG, target_dir,
            use_mirror=False, timeout=180,
        )
        if not ok_install:
            info("默认源失败，尝试清华镜像 ...")
            ok_install, err = _pip_target_install(
                sys.executable, HEALTH_TEST_PKG, target_dir,
                use_mirror=True, timeout=180,
            )
        if not ok_install:
            warn("安装失败：")
            for line in err.splitlines():
                print("      " + line)
            return False

        info("测试 2/2：验证 import ...")
        code = (
            "import sys; "
            "sys.path.insert(0, r'%s'); "
            "import %s; "
            "print(%s.__version__)"
            % (str(target_dir), HEALTH_TEST_PKG, HEALTH_TEST_PKG)
        )
        try:
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                warn("导入失败：")
                for line in (r.stderr or "").splitlines()[-5:]:
                    print("      " + line)
                return False
        except Exception as e:
            warn("导入验证异常: %s" % e)
            return False

        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 下载与解压独立 Python（b）
# ═══════════════════════════════════════════════════════════════

def build_download_url(mirror_prefix, target_triple):
    filename = "cpython-%s+%s-%s-install_only.tar.gz" % (
        PYTHON_VERSION, PBS_RELEASE_TAG, target_triple
    )
    filename_encoded = filename.replace("+", "%2B")
    return mirror_prefix + PBS_RELEASE_TAG + "/" + filename_encoded


def download_with_progress(url, dest):
    info("下载: %s" % url)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "ai-terminal-installer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = resp.headers.get("Content-Length")
            total = int(total) if total else None
            downloaded = 0
            chunk_size = 1024 * 256
            last_pct = -1
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        if pct != last_pct and pct % 5 == 0:
                            print("       %d%% (%d/%d MB)" % (
                                pct, downloaded // 1048576, total // 1048576
                            ))
                            last_pct = pct
        return True
    except urllib.error.HTTPError as e:
        warn("HTTP %d" % e.code)
        return False
    except urllib.error.URLError as e:
        warn("连接失败: %s" % e.reason)
        return False
    except Exception as e:
        warn("下载出错: %s" % e)
        return False


def download_python(target_triple):
    tmp_dir = Path(tempfile.mkdtemp(prefix="ai_term_"))
    archive_path = tmp_dir / "python.tar.gz"

    for mirror in MIRRORS:
        url = build_download_url(mirror, target_triple)
        info("尝试镜像: %s" % mirror.split("/")[2])
        if download_with_progress(url, archive_path):
            ok("下载成功")
            return archive_path, tmp_dir
        warn("该镜像失败，尝试下一个...")
        print()

    error("所有镜像均下载失败。")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None, None


def _is_safe_tar_member(member):
    name = member.name
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = Path(name).parts
    if ".." in parts:
        return False
    return True


def extract_python(archive_path):
    info("解压 Python 运行时 ...")
    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if not _is_safe_tar_member(member):
                    error("tar 包含不安全路径: %s" % member.name)
                    return False
            if sys.version_info >= (3, 12):
                tf.extractall(RUNTIME_DIR, filter="tar")
            else:
                tf.extractall(RUNTIME_DIR)
    except Exception as e:
        error("解压失败: %s" % e)
        return False

    py = runtime_python()
    if not py.exists():
        error("解压后未找到 Python 可执行文件")
        return False

    if not is_windows():
        try:
            os.chmod(py, 0o755)
        except Exception:
            pass

    ok("Python 运行时已就绪")
    return True


def install_runtime():
    """下载并安装独立 Python 运行时。成功返回 True。"""
    try:
        target_triple = get_platform_info()
    except RuntimeError as e:
        error(str(e))
        return False

    info("平台: %s" % target_triple)
    info("将下载独立 Python %s" % PYTHON_VERSION)
    print()

    archive_path, tmp_dir = download_python(target_triple)
    if archive_path is None:
        return False

    try:
        if not extract_python(archive_path):
            return False
        if not install_deps(runtime_python()):
            return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return True


# ═══════════════════════════════════════════════════════════════
# 创建本地 venv（c）
# ═══════════════════════════════════════════════════════════════

def create_venv():
    info("创建本地虚拟环境 venv/ ...")
    if VENV_DIR.exists():
        warn("venv/ 已存在，将重建。")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        error("创建 venv 失败: %s" % e)
        return False

    py = venv_python()
    if not py.exists():
        error("创建 venv 后找不到 Python 可执行文件")
        return False

    ok("venv 已创建")
    return True


def install_venv():
    """创建 venv 并安装依赖。成功返回 True。"""
    if RUNTIME_DIR.exists():
        warn("检测到旧的 runtime/ 目录，选择 venv 方案时不需要它，将删除。")
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    if not create_venv():
        return False
    if not install_deps(venv_python()):
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# 释放内嵌文件
# ═══════════════════════════════════════════════════════════════

def write_embedded_files():
    info("释放主程序 ...")
    try:
        (SCRIPT_DIR / "ai_terminal.py").write_text(
            AI_TERMINAL_PY, encoding="utf-8"
        )
        ok("ai_terminal.py 已写入")
    except Exception as e:
        error("写入 ai_terminal.py 失败: %s" % e)

    try:
        (SCRIPT_DIR / "README.md").write_text(
            README_MD, encoding="utf-8"
        )
        ok("README.md 已写入")
    except Exception as e:
        error("写入 README.md 失败: %s" % e)


# ═══════════════════════════════════════════════════════════════
# 生成启动器
# ═══════════════════════════════════════════════════════════════

def create_launchers():
    if is_windows():
        content = (
            "@echo off\r\n"
            "REM ai-terminal launcher\r\n"
            'set "DIR=%~dp0"\r\n'
            'if exist "%DIR%runtime\\python\\python.exe" (\r\n'
            '    set "PY=%DIR%runtime\\python\\python.exe"\r\n'
            ") else if exist \"%DIR%venv\\Scripts\\python.exe\" (\r\n"
            '    set "PY=%DIR%venv\\Scripts\\python.exe"\r\n'
            ") else (\r\n"
            "    echo Python runtime not found. Please rerun the installer.\r\n"
            "    pause\r\n"
            "    exit /b 1\r\n"
            ")\r\n"
            '"%PY%" "%DIR%ai_terminal.py" %*\r\n'
            "if errorlevel 1 pause\r\n"
        )
        path = SCRIPT_DIR / "ai-term.bat"
        try:
            path.write_bytes(content.encode("ascii"))
            ok("ai-term.bat 已生成 (Windows)")
        except Exception as e:
            warn("生成 ai-term.bat 失败: %s" % e)
    else:
        content = (
            "#!/bin/bash\n"
            "# ai-terminal launcher\n"
            'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
            'if [ -x "$DIR/runtime/python/bin/python3" ]; then\n'
            '    PY="$DIR/runtime/python/bin/python3"\n'
            'elif [ -x "$DIR/venv/bin/python3" ]; then\n'
            '    PY="$DIR/venv/bin/python3"\n'
            "else\n"
            '    echo "找不到 Python 运行环境，请重新运行安装脚本。" >&2\n'
            "    exit 1\n"
            "fi\n"
            'exec "$PY" "$DIR/ai_terminal.py" "$@"\n'
        )
        path = SCRIPT_DIR / "ai-term"
        try:
            path.write_text(content, encoding="utf-8")
            os.chmod(path, 0o755)
            ok("ai-term 已生成 (Linux/macOS)")
        except Exception as e:
            warn("生成 ai-term 失败: %s" % e)


# ═══════════════════════════════════════════════════════════════
# 收尾
# ═══════════════════════════════════════════════════════════════

def finish(kind):
    print()
    write_embedded_files()
    create_launchers()
    (SCRIPT_DIR / "chat").mkdir(exist_ok=True)

    print()
    banner("安装完成")
    print("安装目录: %s" % SCRIPT_DIR)
    if kind == "runtime":
        print("运行环境: 独立 Python %s（runtime/）" % PYTHON_VERSION)
    else:
        print("运行环境: 系统 Python + 本地 venv（venv/）")
    print()
    print("接下来:")
    print()
    if is_windows():
        print("  1. 双击 ai-term.bat 启动")
    else:
        print("  1. 运行 ./ai-term 启动")
    print("  2. 首次启动会自动生成 config.toml")
    print("  3. 编辑 config.toml 填入 API key，按 Ctrl+R 重载")
    print()


def exit_user_cancelled():
    warn("用户选择退出。")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    banner("AI 终端 - 一键安装/修复")

    sys_ver_str = ".".join(str(x) for x in sys.version_info[:3])
    print("脚本目录: %s" % SCRIPT_DIR)
    print("系统 Python: %s" % sys_ver_str)
    print("Python 路径: %s" % sys.executable)
    print()

    # ── Step 0: 已有可用环境 ──
    _, existing_kind = find_usable_env()
    if existing_kind is not None:
        ok("已存在可用的环境（%s），跳过下载。" % existing_kind)
        finish(existing_kind)
        return

    # ── Step 1 (a): 检查系统 Python 版本 ──
    sys_ok = sys.version_info >= MIN_PY_FOR_MAIN

    if not sys_ok:
        warn("系统 Python 版本 %s 低于主程序要求（>= %d.%d）。"
             % (sys_ver_str, MIN_PY_FOR_MAIN[0], MIN_PY_FOR_MAIN[1]))
        print()
        print("  主程序用到了 tomllib，这是 Python 3.11 才加入标准库的模块。")
        print("  需要下载一个独立的 Python %s 环境才能运行。" % PYTHON_VERSION)
        print()
        ans = ask_three_way(
            "是否下载完整所需版本的免安装 Python 环境？", default=False
        )
        if ans is True:
            print()
            if not install_runtime():
                error("安装独立环境失败。")
                sys.exit(1)
            finish("runtime")
        else:
            exit_user_cancelled()
        return

    # 系统 Python >= 3.11
    info("系统 Python 版本 %s 满足主程序要求（>= %d.%d）。"
         % (sys_ver_str, MIN_PY_FOR_MAIN[0], MIN_PY_FOR_MAIN[1]))
    print()
    print("  下一步将测试当前 Python 的 pip 健康度：")
    print("  在临时目录里装一个小包（%s），并尝试 import。" % HEALTH_TEST_PKG)
    print("  这一步可以识别出沙箱版 / 精简版 / 配置异常的 Python。")
    print()
    ans = ask_three_way("是否开始环境测试？", default=True)
    if ans is None:
        exit_user_cancelled()
    if ans is False:
        print()
        info("跳过测试，直接下载独立环境 ...")
        if not install_runtime():
            error("安装独立环境失败。")
            sys.exit(1)
        finish("runtime")
        return

    # ── Step 2 (d): 测试 pip 健康度 ──
    print()
    healthy = test_pip_health()

    if healthy:
        ok("环境测试通过。")
        print()
        ans = ask_three_way("是否用系统 Python 创建本地 venv？", default=True)
        if ans is None:
            exit_user_cancelled()
        if ans is False:
            print()
            info("改为下载独立环境 ...")
            if not install_runtime():
                error("安装独立环境失败。")
                sys.exit(1)
            finish("runtime")
            return

        # ── Step 4 (c): 装 venv ──
        print()
        if not install_venv():
            error("创建 venv / 安装依赖失败。")
            sys.exit(1)
        finish("venv")
        return

    # 环境测试失败
    warn("环境测试失败。")
    print()
    print("  可能原因：")
    print("    - 当前 Python 是 Microsoft Store 沙箱版 / pythoncore 精简版，")
    print("      pip 无法正常下载或导入包")
    print("    - pip 配置指向了不可用的源")
    print("    - 网络不通或代理设置异常")
    print("    - 权限或磁盘空间问题")
    print()
    ans = ask_three_way("是否下载独立环境？", default=False)
    if ans is True:
        print()
        if not install_runtime():
            error("安装独立环境失败。")
            sys.exit(1)
        finish("runtime")
    else:
        exit_user_cancelled()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("用户中断")
        sys.exit(1)
