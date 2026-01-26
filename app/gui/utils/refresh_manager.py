
# refresh_manager
# app.gui.utils.refresh_manager.py

# app/gui/utils/refresh_manager.py

import streamlit as st
from app.core.cache_manager import (
    update_all_cache,
    update_main_account_cache,
    update_client_cache
)
from app.core.logger import logger


def refresh_current_page():
    """Обновить текущую страницу по правилам (API запрос)"""

    if st.session_state.get('show_main_account_edit'):
        logger.info("Refreshing: Main Account Management")
        refresh_main_account_page()

    elif st.session_state.get('show_client_management'):
        logger.info("Refreshing: Client Management")
        refresh_client_management_page()

    elif st.session_state.get('show_synchronization'):
        logger.info("Refreshing: Sync Panel")
        refresh_sync_panel_page()

    elif st.session_state.get('selected_client_id'):
        client_id = st.session_state.selected_client_id
        logger.info(f"Refreshing: Client Details ({client_id})")
        refresh_client_details_page(client_id)

    else:
        logger.info("Refreshing: Dashboard")
        refresh_dashboard_page()


def refresh_dashboard_page():
    """Обновить Dashboard (API запрос)"""
    update_all_cache()


def refresh_main_account_page():
    """Обновить Main Account Management (API запрос)"""
    update_main_account_cache()
    reset_main_account_forms()
    st.session_state.main_account_tab = 'Account Information'


def refresh_client_management_page():
    """Обновить Clients Account Management (API запрос)"""
    update_all_cache()  # Обновить данные через API
    reset_client_management_forms()
    st.session_state.client_management_tab = 'General Settings'


def refresh_sync_panel_page():
    """Обновить Sync Panel (API запрос)"""
    update_all_cache()
    st.session_state.sync_panel_tab = 'Auto Sync'


def refresh_client_details_page(client_id: str):
    """Обновить страницу клиента (API запрос)"""
    update_client_cache(client_id)
    st.session_state.client_details_tab = 'Account Information'


# ═══════════════════════════════════════════════════════════════
# НАВИГАЦИЯ (без API запроса, только из кэша)
# ═══════════════════════════════════════════════════════════════

def navigate_to_dashboard():
    """Перейти на Dashboard (без API)"""
    logger.debug("Navigating to Dashboard")
    # Данные из кэша, не обновляем


def navigate_to_main_account():
    """Перейти на Main Account Management (без API)"""
    logger.debug("Navigating to Main Account Management")
    reset_main_account_forms()
    st.session_state.main_account_tab = 'Account Information'


def navigate_to_client_management():
    """Перейти на Client Management (без API)"""
    logger.debug("Navigating to Client Management")
    reset_client_management_forms()
    st.session_state.client_management_tab = 'General Settings'


def navigate_to_sync_panel():
    """Перейти на Sync Panel (без API)"""
    logger.debug("Navigating to Sync Panel")
    st.session_state.sync_panel_tab = 'Auto Sync'


def navigate_to_client_details(client_id: str):
    """Перейти на страницу клиента (без API)"""
    logger.debug(f"Navigating to Client Details: {client_id}")
    st.session_state.client_details_tab = 'Account Information'


# ═══════════════════════════════════════════════════════════════
# СБРОС ФОРМ
# ═══════════════════════════════════════════════════════════════

def reset_main_account_forms():
    """Сбросить формы Main Account (Edit Main Account)"""

    # Увеличить счетчик для сброса форм
    if 'main_form_reset_counter' in st.session_state:
        st.session_state.main_form_reset_counter += 1
    else:
        st.session_state.main_form_reset_counter = 0

    logger.debug(f"Main account forms reset (counter: {st.session_state.main_form_reset_counter})")


def reset_client_management_forms():
    """Сбросить формы Client Management (Add/Remove Client)"""

    # Счетчик для Add New Client
    if 'add_client_form_counter' in st.session_state:
        st.session_state.add_client_form_counter += 1
    else:
        st.session_state.add_client_form_counter = 0

    # Счетчик для Remove Client
    if 'remove_client_form_counter' in st.session_state:
        st.session_state.remove_client_form_counter += 1
    else:
        st.session_state.remove_client_form_counter = 0

    # Сбросить выбранного клиента для удаления
    st.session_state.client_to_delete = None
    st.session_state.show_delete_modal = False

    logger.debug("Client management forms reset")


def reset_all_forms():
    """Сбросить все формы"""
    reset_main_account_forms()
    reset_client_management_forms()
