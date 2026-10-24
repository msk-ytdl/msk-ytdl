@echo off
setlocal enabledelayedexpansion
title MSK-YTDL Executable & Portable Packager
cd /d "%~dp0"

echo =========================================================
echo   MSK-YTDL: Windows Executable & Portable Packager
echo   Bundles standalone EXE, FFmpeg, and shareable ZIP
echo =========================================================
echo.

if exist ".\.venv\Scripts\python.exe" (
    echo [INFO] Using virtual environment Python...
    ".\.venv\Scripts\python.exe" build_exe.py %*
) else (
    echo [INFO] Using system Python...
    python build_exe.py %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build process failed with exit code %ERRORLEVEL%.
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [DONE] Build completed successfully!
pause
