
# app_streamlit_multi.py
# .app_gui

# streamlit run app_streamlit_multi.py
# Get-Content logs/schwab_client.log -Wait -Encoding UTF8
# python scripts/count_lines.py

# Remove-Item -Recurse -Force .git
# git init
# git add .
# git commit -m "Multi-client Position Copier v1.40"
# git remote add origin https://github.com/leozex777/SyncSchwab
# git remote --v
# git branch -M main
# git push -u origin main --force

# pip install streamlit
# python -m pip uninstall streamlit
# python -m pip cache purge

import streamlit as st


# ═══════════════════════════════════════════════════
# ЛОГГЕР - ОДИН РАЗ ПРИ СТАРТЕ
# ═══════════════════════════════════════════════════
@st.cache_resource
def init_logger():
    """Инициализация логера - выполняется один раз"""
    from app.core.logger import setup_logger

    # console=False - НЕ выводить в консоль (быстрее)
    # console=True - выводить в консоль (для отладки)
    setup_logger(level="INFO", console=False)

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
