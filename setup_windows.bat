@echo off
setlocal enabledelayedexpansion

echo =======================================================
echo          MSK-YTDL: Windows Environment Setup
echo =======================================================
echo.

:: 1. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on your system PATH.
    echo Please install Python 3.11 or later from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check Python Version (>= 3.11 required)
for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2^>nul') do set PY_VER=%%i
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Detected Python version %PY_VER% which does not satisfy the requirement: Python 3.11 or later.
    echo Please upgrade Python to version 3.11 or newer.
    echo.
    pause
    exit /b 1
)
echo [OK] Python %PY_VER% detected.

:: 3. Create Virtual Environment (.venv) if missing
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment in .venv ...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment .venv already exists.
)

:: 4. Upgrade pip and install project dependencies
echo [INFO] Upgrading pip in virtual environment ...
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo [INFO] Installing MSK-YTDL dependencies: yt-dlp, yt-dlp-ejs, rich, pytest ...
.\.venv\Scripts\python.exe -m pip install -e . --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency installation failed.
    echo.
    pause
    exit /b 1
)
echo [OK] MSK-YTDL package and dependencies installed successfully.

:: 5. System Dependency Checks (FFmpeg, FFprobe, JS Runtime)
echo.
echo -------------------------------------------------------
echo           Checking External Dependencies
echo -------------------------------------------------------

ffmpeg -version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] FFmpeg found on system PATH.
) else (
    echo [WARNING] FFmpeg is not installed or not on system PATH.
    echo           FFmpeg is required to merge video/audio streams and convert to MP3.
    echo           To install on Windows, run: winget install Gyan.FFmpeg
    echo           Or download from: https://www.gyan.dev/ffmpeg/builds/
)

ffprobe -version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] FFprobe found on system PATH.
) else (
    echo [NOTE] FFprobe not detected - optional stream analyzer bundled with FFmpeg.
)

set JS_FOUND=0
deno --version >nul 2>&1 && (
    echo [OK] JavaScript Runtime - Deno detected.
    set JS_FOUND=1
)
if !JS_FOUND! equ 0 (
    node -v >nul 2>&1 && (
        echo [OK] JavaScript Runtime - Node.js detected.
        set JS_FOUND=1
    )
)
if !JS_FOUND! equ 0 (
    echo [WARNING] No external JavaScript runtime: Deno or Node.js found.
    echo           YouTube signature challenges often require Deno or Node.js.
    echo           To install Deno, open PowerShell and run:
    echo             irm https://deno.land/install.ps1 ^| iex
    echo           Or install Node.js: winget install OpenJS.NodeJS.LTS
)

echo.
echo =======================================================
echo          Setup Completed Successfully!
echo =======================================================
echo You can now launch MSK-YTDL by running:
echo   run.bat
echo Or:
echo   .\.venv\Scripts\python.exe -m youtube_downloader
echo.
pause
exit /b 0
