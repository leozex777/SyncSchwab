@echo off
chcp 65001 >nul

goto :skip_comment
.\start_gui.bat
.\start_worker.bat
Get-Content logs/app_schwab.log -Wait -Encoding UTF8
python scripts/count_lines.py
python scripts/project_structure.py --path . --stats --output scripts/structure.txt

Remove-Item -Recurse -Force .git
git init
git add .
git commit -m "v2.15: Worker background mode improvements - Streamlit warnings fix, GUI sync timer"
git commit -m "v2.16: GUI auto-refresh fix - st.rerun(scope=app), sync timer reset on Stop, worker status from file"
git commit -m "v2.17: GUI-Worker sync, single instance protection, Modern Standby (S0) support, modal X button fix"
git commit -m "v2.18: Monitor Mode GUI, Apply command, market hours check for Simulation modes"
git commit -m "v2.19: FIXED_AMOUNT protected equity, usage_percent for DYNAMIC_RATIO, sync_worker reads market hours from settings"
git commit -m "v2.20: Monitor Simulation Delta with market flags, history 6 months, logs 4 weeks"
git commit -m "v2.21: Simulation Mode, client cache cleanup on stop/auth, GUI stdout/stderr filters for schwab messages"

git remote add origin https://github.com/leozex777/SyncSchwab
git remote --v
git branch -M main
git push -u origin main --force

:skip_comment
echo.
echo   SyncSchwab GUI Starting...
echo   Press Ctrl+C to stop
echo.

streamlit run app_streamlit_multi.py