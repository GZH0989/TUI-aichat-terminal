@echo off
REM ============================================================
REM  ai-terminal installer (Windows)
REM ============================================================
REM  Usage:
REM    Double-click this file, or run it in cmd:
REM      install.bat
REM
REM  Notes:
REM    - Everything is installed into the folder containing this file.
REM    - Generates ai-term.bat launcher. You can move the folder freely.
REM    - Idempotent: safe to re-run.
REM ============================================================

setlocal EnableDelayedExpansion

REM Directory of this script (with trailing backslash)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%venv"
set "LAUNCHER=%SCRIPT_DIR%ai-term.bat"
set "CHAT_DIR=%SCRIPT_DIR%chat"

echo.
echo ============================================================
echo   ai-terminal installer
echo ============================================================
echo.
echo Install location: %SCRIPT_DIR%
echo.

REM -- Check Python -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python not found.
    echo.
    echo Please install Python 3.11 or newer:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM -- Check Python version (via tomllib, present since 3.11) --
python -c "import tomllib" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python version too old. Need 3.11 or newer.
    echo.
    python --version
    echo.
    echo Download newer version: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [ OK ] Python check passed.
python --version

REM -- Check main script --------------------------------------
if not exist "%SCRIPT_DIR%ai_terminal.py" (
    echo [FAIL] ai_terminal.py not found in this folder.
    echo        Put it next to install.bat.
    pause
    exit /b 1
)

REM -- Create virtual environment -----------------------------
if exist "%VENV_DIR%" (
    echo [INFO] venv already exists, skipping creation.
) else (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [FAIL] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [ OK ] Virtual environment created.
)

REM -- Install dependencies -----------------------------------
echo [INFO] Installing dependencies (aiohttp, prompt_toolkit)...
"%VENV_DIR%\Scripts\pip.exe" install --quiet --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install --quiet aiohttp prompt_toolkit
if errorlevel 1 (
    echo [FAIL] Failed to install dependencies.
    pause
    exit /b 1
)
echo [ OK ] Dependencies installed.

REM -- chat directory -----------------------------------------
if not exist "%CHAT_DIR%" mkdir "%CHAT_DIR%"
echo [ OK ] chat directory ready.

REM -- Generate launcher --------------------------------------
echo [INFO] Generating launcher...
(
    echo @echo off
    echo REM ai-terminal launcher
    echo REM Resolves its own location, then runs the venv Python.
    echo REM The folder can be moved anywhere.
    echo set "DIR=%%~dp0"
    echo "%%DIR%%venv\Scripts\python.exe" "%%DIR%%ai_terminal.py" %%*
) > "%LAUNCHER%"
echo [ OK ] Launcher created: %LAUNCHER%

REM -- Done ----------------------------------------------------
echo.
echo ============================================================
echo   Installation complete
echo ============================================================
echo.
echo Next steps:
echo.
echo   1. Start the program (double-click or run):
echo        ai-term.bat
echo      On first run, config.toml is generated automatically.
echo.
echo   2. When you see "API key not configured" error,
echo      edit config.toml and fill in your API key:
echo        %SCRIPT_DIR%config.toml
echo.
echo   3. In the running program, press Ctrl+R to reload config.
echo.
echo Tips:
echo   - To create a desktop shortcut: right-click ai-term.bat
echo     -^> Send to -^> Desktop (create shortcut)
echo   - The whole folder can be moved anywhere.
echo.

pause
