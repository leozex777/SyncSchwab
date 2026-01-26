@echo off

REM start_all.bat
REM .\start_all.bat

echo ════════════════════════════════════════════════════════════
echo   SyncSchwab - Starting Services
echo ════════════════════════════════════════════════════════════
echo.

REM Check that we are in the correct directory
if not exist "app_streamlit_multi.py" (
    echo ERROR: app_streamlit_multi.py not found!
    echo Please run this script from the SyncSchwab directory.
    pause
    exit /b 1
)

REM Create the logs folder if it doesn't exist.
if not exist "logs" mkdir logs

REM Create an empty log file if it does not exist.
if not exist "logs\app_schwab.log" type nul > "logs\app_schwab.log"

REM 1. Launch Streamlit GUI
echo [1/3] Starting Streamlit GUI...
start "SyncSchwab GUI" cmd /k "streamlit run app_streamlit_multi.py"

REM Wait 3 seconds
timeout /t 3 /nobreak >nul

REM 2. Run Sync Worker with auto-restart
echo [2/3] Starting Sync Worker...
start "SyncSchwab Worker" cmd /k "call start_worker.bat"

REM Wait 2 seconds
timeout /t 2 /nobreak >nul

REM 3. Launch Log Viewer
echo [3/3] Starting Log Viewer...
start "SyncSchwab Logs" powershell -NoExit -Command "Get-Content logs/app_schwab.log -Wait -Encoding UTF8"

echo.
echo ════════════════════════════════════════════════════════════
echo   All services started!
echo.
echo   GUI:    http://localhost:8501
echo   Worker: Running in background
echo   Logs:   Real-time log viewer
echo.
echo   To stop: Close all command windows
echo ════════════════════════════════════════════════════════════
echo.

pause
