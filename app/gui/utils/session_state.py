
# session_state.py
# app.gui.utils.session_state

import streamlit as st


def init_session_state():
    """Инициализация session state переменных"""

    if 'sync_results' not in st.session_state:
        st.session_state.sync_results = {}

    if 'show_sync_results_modal' not in st.session_state:
        st.session_state.show_sync_results_modal = False

    if 'sync_form_counter' not in st.session_state:
        st.session_state.sync_form_counter = 0

    if 'sync_panel_tab' not in st.session_state:
        st.session_state.sync_panel_tab = 'Auto Sync'

    if 'general_settings_form_counter' not in st.session_state:
        st.session_state.general_settings_form_counter = 0

    if 'show_live_mode_modal' not in st.session_state:
        st.session_state.show_live_mode_modal = False

    if 'pending_general_settings' not in st.session_state:
        st.session_state.pending_general_settings = {}

    if 'auth_errors' not in st.session_state:
        st.session_state.auth_errors = {}

    # ═══════════════════════════════════════════════════════════════
    # ОСНОВНЫЕ КОМПОНЕНТЫ
    # ═══════════════════════════════════════════════════════════════

    if 'client_manager' not in st.session_state:
        from app.models.clients.client_manager import ClientManager
        st.session_state.client_manager = ClientManager()

        # Загрузить account_hash из кэша если нет в clients.json
        if not st.session_state.client_manager.main_account.get('account_hash'):
            from app.core.json_utils import load_json
            from app.core.paths import DATA_DIR

            cache_file = DATA_DIR / "account_cache.json"
            cached_data = load_json(str(cache_file), default={})
            main_cached = cached_data.get('main_account', {})

            if main_cached.get('account_hash'):
                st.session_state.client_manager.set_main_account(
                    account_hash=main_cached['account_hash'],
                    account_number=main_cached.get('account_number', '')
                )

    # ═══════════════════════════════════════════════════════════════
    # НАВИГАЦИЯ
    # ═══════════════════════════════════════════════════════════════

    if 'show_main_account_edit' not in st.session_state:
        st.session_state.show_main_account_edit = False

    if 'show_client_management' not in st.session_state:
        st.session_state.show_client_management = False

    if 'show_synchronization' not in st.session_state:
        st.session_state.show_synchronization = False

    if 'show_log_file' not in st.session_state:
        st.session_state.show_log_file = False

    if 'selected_client_id' not in st.session_state:
        st.session_state.selected_client_id = None

    # ═══════════════════════════════════════════════════════════════
    # МОДАЛЬНЫЕ ОКНА
    # ═══════════════════════════════════════════════════════════════

    if 'show_delete_modal' not in st.session_state:
        st.session_state.show_delete_modal = False

    if 'client_to_delete' not in st.session_state:
        st.session_state.client_to_delete = None

    if 'copier_mode' not in st.session_state:
        st.session_state.copier_mode = 'STOPPED'

    if 'show_sync_modal' not in st.session_state:
        st.session_state.show_sync_modal = False

    if 'show_start_modal' not in st.session_state:
        st.session_state.show_start_modal = False

    if 'show_close_all_modal' not in st.session_state:
        st.session_state.show_close_all_modal = False

    if 'show_close_results_modal' not in st.session_state:
        st.session_state.show_close_results_modal = False

    if 'close_results' not in st.session_state:
        st.session_state.close_results = {}

    # ═══════════════════════════════════════════════════════════════
    # ВКЛАДКИ (стартовые значения)
    # ═══════════════════════════════════════════════════════════════

    if 'main_account_tab' not in st.session_state:
        st.session_state.main_account_tab = 'Account Information'

    if 'client_management_tab' not in st.session_state:
        st.session_state.client_management_tab = 'General Settings'

    # sync_panel_tab уже определен выше!

    if 'client_details_tab' not in st.session_state:
        st.session_state.client_details_tab = 'Account Information'

    # ═══════════════════════════════════════════════════════════════
    # СЧЕТЧИКИ ДЛЯ СБРОСА ФОРМ
    # ═══════════════════════════════════════════════════════════════

    if 'main_form_reset_counter' not in st.session_state:
        st.session_state.main_form_reset_counter = 0

    if 'add_client_form_counter' not in st.session_state:
        st.session_state.add_client_form_counter = 0

    if 'remove_client_form_counter' not in st.session_state:
        st.session_state.remove_client_form_counter = 0