@echo off
setlocal

:: Verify virtual environment exists
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv was not found.
    echo Please run setup first by executing:
    echo   setup_windows.bat
    echo.
    pause
    exit /b 1
)

:: Run MSK-YTDL CLI application with forwarded arguments
"%~dp0.venv\Scripts\python.exe" -m youtube_downloader %*
set APP_EXIT_CODE=%ERRORLEVEL%

:: If an error occurred and no arguments were passed (interactive double-click launch)
if %APP_EXIT_CODE% neq 0 (
    if "%~1"=="" (
        echo.
        echo [NOTICE] Application terminated with exit code %APP_EXIT_CODE%.
        pause
    )
)

exit /b %APP_EXIT_CODE%
