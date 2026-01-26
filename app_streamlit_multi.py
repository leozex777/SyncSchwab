
# app_streamlit_multi.py
# .app_gui

"""
streamlit run app_streamlit_multi.py
python sync_worker.py
Get-Content logs/app_schwab.log -Wait -Encoding UTF8
python scripts/count_lines.py
python scripts/project_structure.py --path . --stats --output scripts/structure.txt

Remove-Item -Recurse -Force .git
git init
git add .
git commit -m "v2.15: Worker background mode improvements - Streamlit warnings fix, GUI sync timer"
git remote add origin https://github.com/leozex777/SyncSchwab
git remote --v
git branch -M main
git push -u origin main --force
"""
# pip install streamlit
# python -m pip uninstall streamlit
# python -m pip cache purge

import streamlit as st
import warnings
import logging
# Предотвратить сон компьютера
from app.core.power_manager import prevent_sleep_gui
prevent_sleep_gui()

# ═══════════════════════════════════════════════════
# ПОДАВЛЕНИЕ STREAMLIT WARNINGS (ScriptRunContext)
# ═══════════════════════════════════════════════════
# Эти warnings появляются когда фоновые потоки
# (EventScheduler, BackgroundCacheUpdate) работают
# без Streamlit контекста - это нормально и безопасно

warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)


# ═══════════════════════════════════════════════════
# ЛОГГЕР - ОДИН РАЗ ПРИ СТАРТЕ
# ═══════════════════════════════════════════════════
@st.cache_resource
def init_logger():
    """Инициализация логера - выполняется один раз"""
    import os
    from app.core.logger import setup_logger

    # console=False - НЕ выводить в консоль (быстрее)
    # console=True - выводить в консоль (для отладки)
    setup_logger(level=os.getenv("LOG_LEVEL", "INFO"), console=False)

    return True


# Инициализировать логер
init_logger()

# ═══════════════════════════════════════════════════
# ОСТАЛЬНОЙ КОД
# ═══════════════════════════════════════════════════

from app.gui.main import run_app  # noqa: E402

# Настройка страницы
st.set_page_config(
    page_title="Transaction Copyist",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

if __name__ == "__main__":
    run_app()
