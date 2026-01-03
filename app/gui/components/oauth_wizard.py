
# oauth_wizard.py
# app.gui.components.oauth_wizard

"""
OAuth Wizard - DEPRECATED
Используйте Dashboard для авторизации
"""

import streamlit as st


def render_oauth_wizard():
    """
    Устаревший OAuth wizard
    Перенаправляет на новый Dashboard
    """

    st.markdown("### 🔐 Account Authorization")

    st.info("""
    **Authorization has been moved to the Dashboard!**

    The new Dashboard provides a cleaner interface for managing
    authorization for Main Account and all Clients.
    """)

    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        if st.button("🚀 Go to Dashboard", type="primary", width="stretch"):
            # Очистить все флаги навигации
            for key in list(st.session_state.keys()):
                if key.startswith('show_'):
                    st.session_state[key] = False

            # Перезагрузить (Dashboard показывается по умолчанию)
            st.rerun()

    st.markdown("---")

    st.caption("💡 The Dashboard will automatically detect which accounts need authorization")

# Все остальные функции удалены
# Авторизация теперь обрабатывается через:
# - app/gui/components/dashboard.py (UI)
# - app/utils/schwab_auth.py (логика)