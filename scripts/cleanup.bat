@echo off

goto :skip_comment
REM =============================================================
.\scripts\cleanup.bat
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*sync_worker*' } | Select-Object ProcessId, ParentProcessId, CommandLine
REM =============================================================

:skip_comment

echo.
echo ============================================================
echo   SyncSchwab - Cleanup Script
echo ============================================================
echo.

REM Перейти в корень проекта (на уровень выше scripts)
cd /d "%~dp0.."

REM Проверить что мы в правильной директории
if not exist "app_streamlit_multi.py" (
    echo ERROR: app_streamlit_multi.py not found!
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Working directory: %CD%
echo.

REM =============================================================
REM KILL RUNNING PROCESSES
REM =============================================================

echo Stopping running processes...
echo.

REM Убить все процессы streamlit (GUI)
taskkill /F /IM streamlit.exe >nul 2>&1 && echo [KILL] streamlit.exe || echo [SKIP] streamlit.exe not running

REM Убить процессы sync_worker.py (исключая текущий PowerShell)
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*sync_worker.py*' } | ForEach-Object { Write-Host '[KILL] sync_worker PID' $_.ProcessId; Stop-Process -Id $_.ProcessId -Force 2>$null }"

echo.
echo Deleting obsolete files...
echo.

REM ============================================================
REM STATUS FILES (reset state)
REM ============================================================

if exist "config\worker_status.json" (
    echo [DEL] config\worker_status.json
    del /q "config\worker_status.json"
)

if exist "config\gui_status.json" (
    echo [DEL] config\gui_status.json
    del /q "config\gui_status.json"
)

REM ============================================================
REM CONFIG FILES (obsolete)
REM ============================================================

if exist "config\auto_sync_state.json" (
    echo [DEL] config\auto_sync_state.json
    del /q "config\auto_sync_state.json"
)

if exist "config\.bg_cache_pid" (
    echo [DEL] config\.bg_cache_pid
    del /q "config\.bg_cache_pid"
)

REM ============================================================
REM DATA FILES (temporary)
REM ============================================================

if exist "data\notifications_queue.json" (
    echo [DEL] data\notifications_queue.json
    del /q "data\notifications_queue.json"
)

if exist "data\.cache_updated" (
    echo [DEL] data\.cache_updated
    del /q "data\.cache_updated"
)

REM ============================================================
REM PYTHON CACHE
REM ============================================================

echo.
echo Cleaning Python cache...

for /d /r %%d in (__pycache__) do (
    if exist "%%d" (
        echo [DEL] %%d
        rd /s /q "%%d"
    )
)

for /r %%f in (*.pyc) do (
    if exist "%%f" (
        echo [DEL] %%f
        del /q "%%f"
    )
)

echo.
echo ============================================================
echo   Cleanup complete!
echo ============================================================
echo.

pause
