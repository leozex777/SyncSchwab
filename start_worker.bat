@echo off
chcp 65001 >nul

goto :skip_comment
REM ==============================================
.\start_worker.bat
REM ==============================================

:skip_comment

:loop
echo.
echo   Sync Worker Starting...
echo   Press Ctrl+C to stop
echo.

python sync_worker.py

REM Check exit code
if %errorlevel%==42 (
    echo.
    echo   ========================================
    echo   Another worker wants to be started!
    echo   Press any key to interrupt the process.
    echo   ========================================
    echo.
    pause
    exit /b 0
)

echo.
echo   Worker stopped or crashed!
echo   Restarting in 10 seconds...
echo   Press Ctrl+C to cancel restart
echo.

timeout /t 10 /nobreak
goto loop
