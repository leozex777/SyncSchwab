
# main.py
# app.gui.main

import sys
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


# Перехват stdout для подавления сообщений schwab библиотеки
class _SchwabMessageFilter:
    """Подавляет сообщения schwab о токене в консоли GUI"""
    _instance = None
    _initialized = False
    
    def __new__(cls, original_stdout):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, original_stdout):
        if not _SchwabMessageFilter._initialized:
            self.original = original_stdout
            self.last_message = None
            _SchwabMessageFilter._initialized = True
    
    def write(self, message):
        msg = message.strip()
        if msg:
            msg_lower = msg.lower()
            # Подавляем сообщения schwab
            is_schwab_message = (
                "refresh token will expire" in msg_lower or
                "refresh_token" in msg_lower or
                "could not get new access token" in msg_lower or
                "error_description" in msg_lower or
                '"error":' in msg_lower or
                "token file does not exist" in msg_lower or
                "no such file or directory" in msg_lower and "tokens" in msg_lower
            )
            
            if is_schwab_message:
                # Не выводить в консоль GUI
                pass
            else:
                self.original.write(message)
        elif message == '\n':
            # Пропускаем пустые строки
            pass
        else:
            self.original.write(message)
            
    def flush(self):
        self.original.flush()


class _SchwabErrorFilter:
    """Подавляет ошибки schwab в stderr"""
    _instance = None
    _initialized = False
    
    def __new__(cls, original_stderr):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, original_stderr):
        if not _SchwabErrorFilter._initialized:
            self.original = original_stderr
            self.buffer = ""
            _SchwabErrorFilter._initialized = True
    
    def write(self, message):
        # Накапливаем сообщения для проверки многострочных ошибок
        self.buffer += message
        
        # Проверяем, нужно ли подавить
        if "schwabdev" in self.buffer.lower() or "client.__del__" in self.buffer.lower():
            # Если встретили конец traceback, очищаем буфер
            if "AttributeError" in self.buffer or self.buffer.endswith("\n\n"):
                self.buffer = ""
            return
        
        # Если не schwab ошибка, выводим
        if message:
            self.original.write(message)
            self.buffer = ""
            
    def flush(self):
        self.original.flush()


# Применить фильтр один раз при импорте модуля
if not isinstance(sys.stdout, _SchwabMessageFilter):
    sys.stdout = _SchwabMessageFilter(sys.stdout)

if not isinstance(sys.stderr, _SchwabErrorFilter):
    sys.stderr = _SchwabErrorFilter(sys.stderr)


def run_app():
    """Главная функция приложения"""

    init_session_state()
    
    # Инициализировать GUI статус (PID, сброс worker)
    _init_gui_status()
    
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


def _init_gui_status():
    """
    Инициализировать GUI статус при старте.
    
    - Записывает PID GUI в файл
    - Сбрасывает worker_status на command: "stop"
    
    Выполняется один раз при старте процесса.
    """
    import os
    from pathlib import Path
    from app.core.json_utils import load_json, save_json
    
    gui_status_file = Path("config/gui_status.json")
    worker_status_file = Path("config/worker_status.json")
    current_pid = os.getpid()
    
    # Проверить — это новый процесс или тот же?
    if gui_status_file.exists():
        try:
            gui_status = load_json(str(gui_status_file), default={})
            saved_pid = gui_status.get("pid")
            if saved_pid == current_pid:
                # Тот же процесс — не сбрасывать
                return
        except (ValueError, OSError):
            pass
    
    # Новый процесс — записать PID и сбросить worker
    gui_status_file.parent.mkdir(parents=True, exist_ok=True)
    save_json(str(gui_status_file), {
        "pid": current_pid,
        "started_at": __import__('datetime').datetime.now().isoformat()
    })
    
    # Сбросить worker_status на "stop"
    worker_status = load_json(str(worker_status_file), default={})
    worker_status["command"] = "stop"
    worker_status["running"] = False
    save_json(str(worker_status_file), worker_status)


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
