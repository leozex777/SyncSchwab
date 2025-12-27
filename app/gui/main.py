
# main.py
# app.gui.main

import streamlit as st
from app.gui.utils.session_state import init_session_state
from app.gui.components import (
    sidebar,
    dashboard,
    main_account,
    client_management,
    client_details,
    synchronization,
    log_viewer,
    modals
)
from app.gui.components.notifications import render_notifications


def run_app():
    """Главная функция приложения"""

    init_session_state()

    # Toast уведомления (проверяет очередь каждые 2 секунды)
    render_notifications()

    sidebar.render()

    # Main Account Management
    if st.session_state.get('show_main_account_edit', False):
        main_account.render()

    # Client Management
    elif st.session_state.get('show_client_management', False):
        client_management.render()

    # Synchronization
    elif st.session_state.get('show_synchronization', False):
        synchronization.render()

    # Log Viewer
    elif st.session_state.get('show_log_file', False):
        log_viewer.render()

    # Client Details
    elif st.session_state.get('selected_client_id'):
        client_details.render()

    # Dashboard (по умолчанию)
    else:
        dashboard.render()

    modals.render_delete_confirmation()
