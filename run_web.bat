@echo off
setlocal
title MSK YTDL: Web App - MSK Software Solutions
cd /d "%~dp0"

echo =========================================================
echo   MSK YTDL: Web Application by MSK Software Solutions
echo   Starting local server and opening browser...
echo =========================================================
echo.

if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" -m youtube_downloader --web
) else (
    python -m youtube_downloader --web
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Web server stopped or encountered an error.
    pause
    exit /b %ERRORLEVEL%
)

pause
