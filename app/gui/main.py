
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
    
    # Запустить фоновое обновление кэша при старте (один раз)
    _start_background_cache_update()

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


def _start_background_cache_update():
    """
    Запустить фоновое обновление кэша при старте GUI.
    
    - GUI запускается сразу (из старого кэша)
    - Фоновый поток пытается обновить кэш
    - Если успех → set_cache_updated(True) → GUI обновится
    - Если ошибка → записать в лог
    
    Использует файловый флаг чтобы не запускать повторно
    при открытии нового браузера в том же процессе.
    """
    import os
    from pathlib import Path
    
    # Файловый флаг (в том же процессе)
    flag_file = Path("config/.bg_cache_pid")
    current_pid = os.getpid()
    
    # Проверить существует ли флаг с текущим PID
    if flag_file.exists():
        try:
            saved_pid = int(flag_file.read_text().strip())
            if saved_pid == current_pid:
                # Уже запущено в этом процессе
                return
        except (ValueError, OSError):
            pass
    
    # Записать текущий PID
    try:
        flag_file.parent.mkdir(parents=True, exist_ok=True)
        flag_file.write_text(str(current_pid))
    except OSError:
        pass
    
    import threading
    from app.core.cache_manager import update_all_cache_background
    
    # Запустить в фоновом потоке
    thread = threading.Thread(
        target=update_all_cache_background,
        name="BackgroundCacheUpdate",
        daemon=True
    )
    thread.start()
