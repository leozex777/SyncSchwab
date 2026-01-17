
# sidebar.py
# app.gui.components.sidebar

import streamlit as st

from app.core.json_utils import load_json
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ИНДИКАТОР КЭША (автообновление каждые 15 сек)
# ═══════════════════════════════════════════════════════════════

@st.fragment(run_every=1)
def render_cache_indicator():
    """
    Индикатор возраста кэша в sidebar.
    Обновляется каждые 15 секунд.
    
    НЕ вызывает st.rerun() - только отображает данные.
    """
    from app.core.cache_manager import format_cache_age
    
    # Отобразить возраст кэша
    time_str, color_emoji = format_cache_age()
    
    st.markdown(
        f"<div style='text-align: center; font-size: 0.9rem; color: gray; margin-bottom: 8px;'>"
        f"{color_emoji} {time_str}</div>",
        unsafe_allow_html=True
    )


@st.fragment(run_every=5)
def render_worker_indicator():
    """
    Индикатор статуса Worker в sidebar.
    Обновляется каждые 5 секунд.
    """
    from app.core.worker_client import format_worker_status_for_display
    
    status_text, emoji = format_worker_status_for_display()
    
    st.markdown(
        f"<div style='text-align: center; font-size: 0.85rem; color: gray; margin-bottom: 8px;'>"
        f"{emoji} {status_text}</div>",
        unsafe_allow_html=True
    )


def render():
    """Отрисовка левой панели"""
    
    # CSS для фиксированной высоты sidebar и расстояний между элементами
    st.markdown("""
        <style>
            [data-testid="stSidebar"] {
                min-height: 100vh;
                max-height: 100vh;
            }
            [data-testid="stSidebar"] > div:first-child {
                height: 100vh;
                overflow-y: auto;
            }
            /* Прижать элементы к верху, фиксированные расстояния */
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
                gap: 0.50rem;
                justify-content: flex-start;
            }
        </style>
    """, unsafe_allow_html=True)

    # Индикатор кэша (над кнопками)
    with st.sidebar:
        render_cache_indicator()
        render_worker_indicator()

    render_control_buttons()

    st.sidebar.title("⚙️ Control Panel")

    render_navigation()

    st.sidebar.markdown("---")

    render_client_list()

    st.sidebar.markdown("---")

    # ========== LOG FILE ==========
    render_log_button()

    st.sidebar.markdown("")

    render_close_all_button()
    
    st.sidebar.markdown("")
    
    # ========== EXIT BUTTON ==========
    render_exit_button()

    render_modals()


def render_log_button():
    """Кнопка просмотра логов"""

    if st.sidebar.button("📋 Log File", width='stretch'):
        reset_modal_flags()
        st.session_state.show_log_file = True
        st.session_state.show_main_account_edit = False
        st.session_state.show_client_management = False
        st.session_state.show_synchronization = False
        st.session_state.selected_client_id = None
        st.rerun()


def render_exit_button():
    """Кнопка выхода из программы и кнопка гашения экрана"""
    
    # Инициализация состояния
    if 'show_exit_confirm' not in st.session_state:
        st.session_state.show_exit_confirm = False
    if 'perform_exit' not in st.session_state:
        st.session_state.perform_exit = False
    
    # Если нужно выполнить выход — делаем это ДО рендера
    if st.session_state.get('perform_exit', False):
        _execute_exit()
        return
    
    # Две кнопки: 🖥️ (1/5) и Exit (4/5)
    col1, col2 = st.sidebar.columns([1, 4])
    
    with col1:
        if st.button("🖥️", help="Turn off display", use_container_width=True):
            _turn_off_display()
    
    with col2:
        if st.button("🚪 Exit", type="secondary", use_container_width=True):
            st.session_state.show_exit_confirm = True
            st.rerun()
    
    # Диалог подтверждения
    if st.session_state.get('show_exit_confirm', False):
        _render_exit_confirmation()


def _turn_off_display():
    """
    Выключить монитор (Windows) - способ для Modern Standby (S0).
    Использует powercfg для изменения таймаута вместо SendMessageW,
    так как SC_MONITORPOWER в S0 вызывает переход в Low Power Idle.
    """
    import sys
    if sys.platform == 'win32':
        import threading
        
        def _do_turn_off():
            import subprocess
            import time
            try:
                # 1. Сохраняем текущий таймаут (для восстановления)
                # 2. Устанавливаем таймаут экрана на 1 секунду
                subprocess.run(
                    ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE", "1"],
                    capture_output=True
                )
                # 3. Применяем настройки
                subprocess.run(
                    ["powercfg", "/setactive", "SCHEME_CURRENT"],
                    capture_output=True
                )
                
                # 4. Ждём пока экран погаснет
                time.sleep(2)
                
                # 5. Возвращаем таймаут в "15 минут" (900 секунд) или "Никогда" (0)
                subprocess.run(
                    ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE", "900"],
                    capture_output=True
                )
                subprocess.run(
                    ["powercfg", "/setactive", "SCHEME_CURRENT"],
                    capture_output=True
                )
            except Exception:
                pass
        
        # Запускаем в отдельном потоке чтобы не блокировать UI
        threading.Thread(target=_do_turn_off, daemon=True).start()


def _render_exit_confirmation():
    """Диалог подтверждения выхода"""
    
    @st.dialog("Exit Application")
    def exit_dialog():
        # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
        st.session_state.show_exit_confirm = False
        
        st.markdown("### Are you sure you want to exit?")
        st.markdown("This will:")
        st.markdown("- Stop Auto Sync (if running)")
        st.markdown("- Allow computer to sleep")
        st.markdown("- Close the application")
        
        # CSS для одинаковых кнопок в диалоге
        st.markdown("""
            <style>
                div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"] {
                    gap: 5rem;
                }
                div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"] > div {
                    flex: 1;
                }
                div[data-testid="stDialog"] button {
                }
            </style>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_exit_confirm = False
                st.rerun()
        
        with col2:
            if st.button("🚪 Exit", use_container_width=True):
                # Устанавливаем флаг и закрываем диалог
                st.session_state.perform_exit = True
                st.session_state.show_exit_confirm = False
                st.rerun()
    
    exit_dialog()


def _execute_exit():
    """Выполнить выход (вызывается после закрытия диалога)"""
    import sys
    import os
    import threading
    from app.core.logger import logger
    
    # Сбросить флаг
    st.session_state.perform_exit = False
    
    try:
        logger.info("🚪 Application exit requested")
        
        # 1. Остановить Worker (отправить команду stop)
        from app.core.worker_client import stop_worker, is_worker_running
        
        if is_worker_running():
            logger.info("Stopping Worker...")
            stop_worker()
        
        # 2. Разрешить сон (для GUI процесса)
        if sys.platform == 'win32':
            try:
                import ctypes
                # ES_CONTINUOUS - сбросить флаги, разрешить сон
                es_continuous = 0x80000000
                # noinspection PyUnresolvedReferences
                ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
                logger.info("[POWER] Sleep allowed")
            except (OSError, AttributeError):
                pass
        
        logger.info("✅ Application shutdown complete")
        logger.info("=" * 50)
        
    except (ImportError, RuntimeError) as e:
        logger.error(f"Error during exit: {e}")
    
    # 4. Показать страницу закрытия и завершить
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] { display: none; }
            [data-testid="stHeader"] { display: none; }
            section[data-testid="stMain"] > div { padding: 0; }
        </style>
        <div style="
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: #0e1117;
            color: #fafafa;
            font-family: sans-serif;
            flex-direction: column;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 9999;
        ">
            <h1>✅ Application Closed</h1>
            <p style="color: #888;">You can close this browser tab</p>
        </div>
        <script>
            // Попытка закрыть вкладку
            setTimeout(function() {
                window.open('', '_self', '');
                window.close();
            }, 500);
        </script>
        """,
        unsafe_allow_html=True
    )
    
    # 5. Завершить Python через 2 секунды
    def delayed_exit():
        import time
        time.sleep(2)
        os._exit(0)
    
    exit_thread = threading.Thread(target=delayed_exit, daemon=True)
    exit_thread.start()
    
    # Остановить дальнейший рендеринг
    st.stop()


def _get_operating_mode() -> str:
    """Получить текущий Operating Mode из general_settings.json"""
    settings_file = Path("config/general_settings.json")
    settings = load_json(str(settings_file), default={"operating_mode": "monitor"})
    return settings.get("operating_mode", "monitor")


def _get_monitor_sync_mode() -> str:
    """Получить режим Sync для Monitor (live/simulation)"""
    settings_file = Path("config/general_settings.json")
    settings = load_json(str(settings_file), default={})
    return settings.get("monitor_sync_mode", "live")


# ════════════════════════════════════════════════════════════════
# ДИАЛОГИ ПОДТВЕРЖДЕНИЯ SYNC / START
# ════════════════════════════════════════════════════════════════

def _render_sync_confirmation():
    """Диалог подтверждения Sync/Apply"""
    operating_mode = _get_operating_mode()
    monitor_sync_mode = _get_monitor_sync_mode()
    is_monitor_mode = (operating_mode == "monitor")
    
    # Определить заголовок и иконку
    if is_monitor_mode:
        if monitor_sync_mode == 'live':
            title = "🔍🔴 Confirm Apply"
            mode_text = "Monitor Live Delta"
        else:
            title = "🔍🔶 Confirm Apply"
            mode_text = "Monitor Simulation Delta"
    elif operating_mode == 'live':
        title = "🔴 Confirm Sync"
        mode_text = "Live Mode"
    else:
        title = "🔶 Confirm Sync"
        mode_text = "Simulation"
    
    @st.dialog(title)
    def sync_dialog():
        # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
        st.session_state.show_sync_confirm = False
        
        st.markdown(f"**Mode:** {mode_text}")
        
        if operating_mode == 'live' or (is_monitor_mode and monitor_sync_mode == 'live'):
            st.warning("⚠️ Real orders will be sent!")
        else:
            st.info("🧪 Simulation - no real orders")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_sync_confirm = False
                st.rerun()
        
        with col2:
            if st.button("✅ Confirm", use_container_width=True):
                st.session_state.perform_sync = True
                st.session_state.show_sync_confirm = False
                st.rerun()
    
    sync_dialog()


def _render_start_confirmation():
    """Диалог подтверждения Start"""
    operating_mode = _get_operating_mode()
    monitor_sync_mode = _get_monitor_sync_mode()
    is_monitor_mode = (operating_mode == "monitor")
    
    # Определить заголовок и иконку
    if is_monitor_mode:
        if monitor_sync_mode == 'live':
            title = "🔍🔴 Confirm Start"
            mode_text = "Monitor Live Delta"
        else:
            title = "🔍🔶 Confirm Start"
            mode_text = "Monitor Simulation Delta"
    elif operating_mode == 'live':
        title = "🔴 Confirm Start"
        mode_text = "Live Mode"
    else:
        title = "🔶 Confirm Start"
        mode_text = "Simulation"
    
    @st.dialog(title)
    def start_dialog():
        # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
        st.session_state.show_start_confirm = False
        
        st.markdown(f"**Mode:** {mode_text}")
        
        if operating_mode == 'live':
            st.warning("⚠️ Auto Sync will send real orders!")
        elif is_monitor_mode and monitor_sync_mode == 'live':
            st.info("🔍 Monitor only - Apply sends real orders")
        else:
            st.info("🧪 Simulation - no real orders")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_start_confirm = False
                st.rerun()
        
        with col2:
            if st.button("✅ Confirm", use_container_width=True):
                st.session_state.perform_start = True
                st.session_state.show_start_confirm = False
                st.rerun()
    
    start_dialog()


def _execute_start(operating_mode: str, is_monitor_mode: bool, monitor_sync_mode: str):
    """Выполнить Start Auto Sync (через Worker)"""
    from app.core.worker_client import start_worker
    from app.core.notification_service import get_notification_service
    from app.models.copier.synchronizer import get_notification_settings
    from app.core.sync_service import get_sync_service
    from datetime import datetime
    from app.core.json_utils import load_json, save_json
    
    sync_service = get_sync_service()
    notif = get_notification_service()
    notif_settings = get_notification_settings()
    
    # Проверить рынок для LIVE режима (Toast один раз при нажатии)
    if operating_mode == 'live' or (is_monitor_mode and monitor_sync_mode == 'live'):
        is_open, reason = sync_service.is_market_open_for_live()
        if not is_open:
            if notif_settings.get('toast_on_error', True):
                notif.warning(f"🔴 Market closed: {reason}")
    
    # Записать start time для Status
    settings = load_json("config/sync_settings.json", default={})
    settings['last_sync_time'] = datetime.now().isoformat()
    save_json("config/sync_settings.json", settings)
    
    # Запустить Worker (отправить команду start)
    success = start_worker()
    
    if success:
        st.session_state.copier_mode = 'AUTO'
        # Toast уведомление
        if notif_settings.get('toast_on_success', False):
            notif.success("▶️ Auto Sync started")
    else:
        st.session_state.copier_mode = 'STOPPED'
        if notif_settings.get('toast_on_error', True):
            notif.error("Failed to start Worker")
    
    st.rerun()


def render_control_buttons():
    """Кнопки управления"""

    from app.gui.utils.refresh_manager import refresh_current_page
    from app.core.worker_client import is_worker_running
    import time

    # ═══════════════════════════════════════════════════════════════
    # ЗАЩИТА ОТ DOUBLE CLICK
    # ═══════════════════════════════════════════════════════════════
    
    debounce_seconds = 0.3  # Минимальный интервал между кликами
    
    def is_button_debounced(button_name: str) -> bool:
        """Проверить прошло ли достаточно времени с последнего клика"""
        key = f"_last_click_{button_name}"
        now = time.time()
        last_click = st.session_state.get(key, 0)
        
        if now - last_click < debounce_seconds:
            return True  # Слишком быстро — игнорировать
        
        st.session_state[key] = now
        return False

    # ═══════════════════════════════════════════════════════════════
    # ВОССТАНОВЛЕНИЕ СОСТОЯНИЯ ИЗ WORKER STATUS
    # ═══════════════════════════════════════════════════════════════
    
    # При первой загрузке проверить файл состояния
    if 'copier_mode' not in st.session_state:
        st.session_state.copier_mode = 'STOPPED'
    
    # Если UI думает что STOPPED, но Worker работает - восстановить
    if st.session_state.copier_mode == 'STOPPED' and is_worker_running():
        st.session_state.copier_mode = 'AUTO'

    mode = st.session_state.get('copier_mode', 'STOPPED')
    operating_mode = _get_operating_mode()
    monitor_sync_mode = _get_monitor_sync_mode()
    is_monitor_mode = (operating_mode == "monitor")

    # ═══════════════════════════════════════════════════════════════
    # ИНИЦИАЛИЗАЦИЯ ФЛАГОВ ПОДТВЕРЖДЕНИЯ
    # ═══════════════════════════════════════════════════════════════
    if 'show_sync_confirm' not in st.session_state:
        st.session_state.show_sync_confirm = False
    if 'show_start_confirm' not in st.session_state:
        st.session_state.show_start_confirm = False
    if 'perform_sync' not in st.session_state:
        st.session_state.perform_sync = False
    if 'perform_start' not in st.session_state:
        st.session_state.perform_start = False
    
    # Выполнить действия если подтверждены
    if st.session_state.get('perform_sync', False):
        st.session_state.perform_sync = False
        if is_monitor_mode:
            _execute_apply_now()
        else:
            _execute_manual_sync()
        return
    
    if st.session_state.get('perform_start', False):
        st.session_state.perform_start = False
        _execute_start(operating_mode, is_monitor_mode, monitor_sync_mode)
        return

    # ═══════════════════════════════════════════════════════════════
    # ИКОНКИ И НАЗВАНИЯ В ЗАВИСИМОСТИ ОТ РЕЖИМА
    # ═══════════════════════════════════════════════════════════════
    if operating_mode == "live":
        sync_icon = "🔴"
        sync_label = "Sync"
        start_icon = "🔴"
        start_label = "Start"
    elif operating_mode == "simulation":
        sync_icon = "🔶"
        sync_label = "Sync"
        start_icon = "🔶"
        start_label = "Start"
    else:  # monitor
        # Monitor режим: иконка зависит от sub-опции
        if monitor_sync_mode == "live":
            sync_icon = "🔍🔴"
            start_icon = "🔍🔴"
        else:
            sync_icon = "🔍🔶"
            start_icon = "🔍🔶"
        sync_label = "Apply"      # Применить дельту
        start_label = "Start"     # Начать мониторинг

    col1, col2, col3 = st.sidebar.columns(3)

    # ===== REFRESH =====
    with col1:
        if st.button("🔄 Refresh", key="btn_refresh", width='stretch'):
            if not is_button_debounced("refresh"):
                reset_modal_flags()
                refresh_current_page()
                st.rerun()

    # ===== SYNC / APPLY =====
    with col2:
        if mode == 'SYNCING':
            st.button(f"⏳ {sync_label}", key="btn_sync", width='stretch', disabled=True)
        elif is_monitor_mode and mode == 'STOPPED':
            # Monitor + STOPPED → Apply заблокирована (нужно сначала включить Monitor)
            st.button(f"{sync_icon} {sync_label}", key="btn_sync", width='stretch', disabled=True)
        elif is_monitor_mode and mode == 'AUTO':
            # Monitor + AUTO → Apply проверяем рабочие часы для Live Delta
            if monitor_sync_mode == 'live':
                # Monitor Live Delta: проверить рабочие часы рынка
                from app.core.sync_service import get_sync_service
                sync_service = get_sync_service()
                is_open, reason = sync_service.is_market_open_for_live()
                if is_open:
                    # Рынок открыт → Apply активна
                    if st.button(f"{sync_icon} {sync_label}", key="btn_sync", width='stretch'):
                        if not is_button_debounced("sync"):
                            reset_modal_flags()
                            st.session_state.show_sync_confirm = True
                            st.rerun()
                else:
                    # Рынок закрыт → Apply заблокирована
                    st.button(f"🔒 {sync_label}", key="btn_sync", width='stretch', disabled=True)
            else:
                # Monitor Simulation Delta → Apply активна (без проверки часов)
                if st.button(f"{sync_icon} {sync_label}", key="btn_sync", width='stretch'):
                    if not is_button_debounced("sync"):
                        reset_modal_flags()
                        st.session_state.show_sync_confirm = True
                        st.rerun()
        elif not is_monitor_mode and mode == 'AUTO':
            # Simulation/Live при AUTO → Sync заблокирована
            st.button(f"{sync_icon} {sync_label}", key="btn_sync", width='stretch', disabled=True)
        else:
            # Simulation/Live при STOPPED → Sync активна
            if st.button(f"{sync_icon} {sync_label}", key="btn_sync", width='stretch'):
                if not is_button_debounced("sync"):
                    reset_modal_flags()
                    st.session_state.show_sync_confirm = True
                    st.rerun()

    # ===== START/STOP / MONITOR =====
    with col3:
        if mode == 'STOPPED':
            if st.button(f"{start_icon} {start_label}", key="btn_start_stop", width='stretch'):
                if not is_button_debounced("start"):
                    reset_modal_flags()
                    if is_monitor_mode:
                        # Monitor режим: Start без подтверждения (не отправляет ордера)
                        _execute_start(operating_mode, is_monitor_mode, monitor_sync_mode)
                    else:
                        # Live/Simulation: показать подтверждение
                        st.session_state.show_start_confirm = True
                        st.rerun()
        elif mode == 'AUTO':
            if st.button("⏹️ Stop", key="btn_start_stop", width='stretch'):
                if not is_button_debounced("stop"):
                    reset_modal_flags()
                    # Остановить Worker (отправить команду stop)
                    from app.core.worker_client import stop_worker
                    stop_worker()
                    st.session_state.copier_mode = 'STOPPED'
                    st.rerun()
        elif mode == 'SYNCING':
            st.button(f"⏳ {start_label}", key="btn_start_stop", width='stretch', disabled=True)
        else:
            st.button(f"{start_icon} {start_label}", key="btn_start_stop", width='stretch', disabled=True)
    
    # ═══════════════════════════════════════════════════════════════
    # ДИАЛОГИ ПОДТВЕРЖДЕНИЯ
    # ═══════════════════════════════════════════════════════════════
    if st.session_state.get('show_sync_confirm', False):
        _render_sync_confirmation()
    
    if st.session_state.get('show_start_confirm', False):
        _render_start_confirmation()


def _execute_apply_now():
    """
    Выполнить Apply немедленно (для Monitor режима).
    
    Использует execute_apply_now() который:
    - Дожидается завершения текущего sync (если выполняется)
    - Выполняет manual sync
    """
    from app.core.sync_service import get_sync_service
    from app.core.notification_service import get_notification_service
    from app.models.copier.synchronizer import get_notification_settings
    
    sync_service = get_sync_service()
    notif = get_notification_service()
    notif_settings = get_notification_settings()
    
    st.session_state.copier_mode = 'SYNCING'
    
    results = sync_service.execute_apply_now()
    
    st.session_state.copier_mode = 'AUTO'  # Вернуть в AUTO (Monitor продолжает работать)
    
    # Показать результат
    if not results:
        if notif_settings['toast_on_error']:
            notif.warning("No sync results")
    elif results.get('status') == 'skipped':
        reason = results.get('reason', 'unknown')
        if notif_settings['toast_on_error']:
            notif.warning(f"Apply skipped: {reason}")
    elif results.get('status') == 'market_closed':
        # LIVE режим: рынок закрыт
        reason = results.get('reason', 'Market closed')
        if notif_settings['toast_on_error']:
            notif.warning(f"🔴 Market closed: {reason}")
    elif results.get('status') == 'error':
        if notif_settings['toast_on_error']:
            notif.error(f"Apply error: {results.get('reason', 'Unknown')}")
    else:
        # Подсчитать итоги
        total_clients = 0
        success_clients = 0
        total_orders = 0
        for client_id, result_data in results.items():
            if isinstance(result_data, dict):
                total_clients += 1
                if result_data.get('status') == 'success':
                    success_clients += 1
                    # Подсчитать ордера
                    sync_result = result_data.get('result', {})
                    total_orders += len(sync_result.get('results', []))
        
        if total_orders > 0:
            if notif_settings['toast_on_success']:
                notif.success(f"Applied: {total_orders} orders for {success_clients}/{total_clients} clients")
        else:
            if notif_settings['toast_on_success']:
                notif.info(f"No orders needed ({success_clients}/{total_clients} clients in sync)")
    
    st.rerun()


def _execute_manual_sync():
    """
    Выполнить Manual Sync сразу (без модального окна).
    
    Если Auto Sync работает (в режиме Monitor), ставит флаг через файл.
    """
    from app.core.sync_service import get_sync_service
    
    sync_service = get_sync_service()
    mode = st.session_state.get('copier_mode', 'STOPPED')
    
    # Если AUTO работает — установить флаг через файл
    if mode == 'AUTO':
        sync_service.set_pending_manual_sync()
        st.toast("⏳ Manual Sync queued, will execute after current Auto Sync")
        st.rerun()
    
    # Выполнить сразу
    st.session_state.copier_mode = 'SYNCING'
    
    results = sync_service.run_manual_sync()
    
    st.session_state.copier_mode = 'STOPPED'
    
    # Показать результат через систему уведомлений (учитывает настройки)
    from app.core.notification_service import get_notification_service
    from app.models.copier.synchronizer import get_notification_settings
    
    notif = get_notification_service()
    notif_settings = get_notification_settings()
    
    if not results:
        if notif_settings['toast_on_error']:
            notif.warning("No sync results")
    elif results.get('status') == 'skipped':
        reason = results.get('reason', 'unknown')
        if notif_settings['toast_on_error']:
            notif.warning(f"Sync skipped: {reason}")
    elif results.get('status') == 'market_closed':
        # LIVE режим: рынок закрыт
        reason = results.get('reason', 'Market closed')
        if notif_settings['toast_on_error']:
            notif.warning(f"🔴 Market closed: {reason}")
    elif results.get('status') == 'error':
        if notif_settings['toast_on_error']:
            notif.error(f"Sync error: {results.get('reason', 'Unknown')}")
    else:
        # Подсчитать итоги
        total_clients = 0
        success_clients = 0
        for client_id, result_data in results.items():
            if isinstance(result_data, dict):
                total_clients += 1
                if result_data.get('status') == 'success':
                    success_clients += 1
        if notif_settings['toast_on_success']:
            notif.success(f"Sync completed: {success_clients}/{total_clients} clients")
    
    st.rerun()


def render_navigation():
    """Навигационные кнопки"""

    from app.gui.utils.refresh_manager import (
        navigate_to_dashboard,
        navigate_to_main_account,
        navigate_to_client_management,
        navigate_to_sync_panel
    )

    # Dashboard
    if st.sidebar.button("🏠 Dashboard", width='stretch'):
        reset_modal_flags()
        navigate_to_dashboard()
        st.session_state.show_main_account_edit = False
        st.session_state.show_client_management = False
        st.session_state.show_synchronization = False
        st.session_state.show_log_file = False
        st.session_state.selected_client_id = None
        st.session_state.show_delete_modal = False
        st.session_state.client_to_delete = None
        st.rerun()

    st.sidebar.markdown("")

    # Main Account Management
    if st.sidebar.button("🏦 Main Account Management", width='stretch'):
        reset_modal_flags()
        navigate_to_main_account()
        st.session_state.show_main_account_edit = True
        st.session_state.show_client_management = False
        st.session_state.show_synchronization = False
        st.session_state.show_log_file = False
        st.session_state.selected_client_id = None
        st.session_state.show_delete_modal = False
        st.session_state.client_to_delete = None
        st.rerun()

    st.sidebar.markdown("")

    # Clients Account Management
    if st.sidebar.button("👥 Clients Account Management", width='stretch'):
        reset_modal_flags()
        navigate_to_client_management()
        st.session_state.show_client_management = True
        st.session_state.show_main_account_edit = False
        st.session_state.show_synchronization = False
        st.session_state.show_log_file = False
        st.session_state.selected_client_id = None
        st.session_state.show_delete_modal = False
        st.session_state.client_to_delete = None
        st.rerun()

    st.sidebar.markdown("")

    # Sync Panel
    if st.sidebar.button("🔄 Sync Panel", width='stretch'):
        reset_modal_flags()
        navigate_to_sync_panel()
        st.session_state.show_synchronization = True
        st.session_state.show_main_account_edit = False
        st.session_state.show_client_management = False
        st.session_state.show_log_file = False
        st.session_state.selected_client_id = None
        st.session_state.show_delete_modal = False
        st.session_state.client_to_delete = None
        st.rerun()


def render_client_list():
    """Список клиентов"""

    from app.gui.utils.refresh_manager import navigate_to_client_details

    st.sidebar.markdown("**👥 Clients**")

    if 'client_manager' not in st.session_state:
        st.sidebar.info("Loading...")
        return

    if st.session_state.client_manager is None:
        st.sidebar.info("Loading...")
        return

    client_manager = st.session_state.client_manager

    if client_manager.clients:
        for client_config in client_manager.clients:
            status_icon = "✅" if client_config.enabled else "⏸️"

            if st.sidebar.button(
                    f"{status_icon} {client_config.name}",
                    key=f"client_btn_{client_config.id}",
                    width='stretch'
            ):
                reset_modal_flags()
                navigate_to_client_details(client_config.id)
                st.session_state.selected_client_id = client_config.id
                st.session_state.show_main_account_edit = False
                st.session_state.show_client_management = False
                st.session_state.show_synchronization = False
                st.session_state.show_log_file = False
                st.session_state.show_delete_modal = False
                st.session_state.client_to_delete = None
                st.rerun()
    else:
        st.sidebar.info("No clients yet")


def render_close_all_button():
    """Кнопка Close all clients positions"""

    mode = st.session_state.get('copier_mode', 'STOPPED')

    if mode == 'CLOSING':
        st.sidebar.button(
            "🛑 Closing...",
            key="btn_close_all",
            width='stretch',
            disabled=True
        )
    else:
        if st.sidebar.button(
                "🛑 Close All",
                key="btn_close_all",
                width='stretch'
        ):
            reset_modal_flags()
            st.session_state.show_close_all_modal = True
            st.rerun()


def render_modals():
    """Отрисовка модальных окон"""

    # CSS для кнопок в модальных окнах
    st.markdown("""
    <style>
    /* Кнопки - белые ВСЕГДА, включая focus */
    div[data-testid="stDialog"] button[data-testid="stBaseButton-secondary"],
    div[data-testid="stDialog"] button[data-testid="stBaseButton-primary"] {
        background-color: #ffffff !important;
        border-color: #e0e0e0 !important;
        color: #333333 !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* ТОЛЬКО при наведении мышкой - голубые */
    div[data-testid="stDialog"] button[data-testid="stBaseButton-secondary"]:hover,
    div[data-testid="stDialog"] button[data-testid="stBaseButton-primary"]:hover {
        background-color: #2196F3 !important;
        border-color: #1976D2 !important;
        color: white !important;
    }

    /* Кнопка X - при наведении */
    div[data-testid="stDialog"] button[aria-label="Close"]:hover {
        background-color: #2196F3 !important;
        color: white !important;
        border-radius: 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Модальные окна
    # show_sync_modal — УБРАНО (Sync выполняется сразу)

    if st.session_state.get('show_start_modal', False):
        show_start_modal()

    if st.session_state.get('show_close_all_modal', False):
        show_close_all_modal()

    if st.session_state.get('show_sync_results_modal', False):
        show_sync_results_modal()


@st.dialog("🧪 Confirm Manual Sync (Dry Run)")
def show_sync_modal():
    """Модальное окно подтверждения ручной синхронизации"""
    # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
    st.session_state.show_sync_modal = False

    from app.core.sync_service import get_sync_service
    
    sync_service = get_sync_service()
    client_ids = sync_service.get_manual_sync_clients()

    st.markdown("**Sync positions for these clients (DRY RUN):**")

    client_manager = st.session_state.client_manager

    if client_ids:
        for client_id in client_ids:
            client = client_manager.get_client(client_id)
            if client:
                scale = client.settings.get('scale_method', 'N/A')
                status = "✅" if client.enabled else "⏸️"
                st.markdown(f"• {status} {client.name} ({scale})")
    else:
        st.warning("No clients selected for sync")

    st.markdown("---")
    st.info("🧪 **DRY RUN MODE** - Orders will NOT be sent to Schwab")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Confirm", key="sync_confirm", width='stretch'):
            st.session_state.show_sync_modal = False
            st.session_state.copier_mode = 'SYNCING'
            
            # Выполнить Manual Sync
            with st.spinner("Syncing..."):
                results = sync_service.run_manual_sync()
            
            st.session_state.copier_mode = 'STOPPED'
            st.session_state.sync_results = results
            st.session_state.show_sync_results_modal = True
            st.rerun()

    with col2:
        if st.button("Cancel", key="sync_cancel", type="primary", width='stretch'):
            st.session_state.show_sync_modal = False
            st.rerun()


@st.dialog("🧪 Confirm Auto Sync (Dry Run)")
def show_start_modal():
    """Модальное окно подтверждения автоматической синхронизации"""
    # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
    st.session_state.show_start_modal = False

    from app.core.sync_service import get_sync_service
    from app.core.json_utils import load_json
    from app.core.worker_client import start_worker
    
    sync_service = get_sync_service()
    client_ids = sync_service.get_auto_sync_clients()
    
    # Получить настройки интервала
    settings = load_json("config/sync_settings.json", default={})
    interval = settings.get('auto_sync_interval', 'Every 5 minutes')

    st.markdown("**Start automatic sync for these clients (DRY RUN):**")

    client_manager = st.session_state.client_manager

    if client_ids:
        for client_id in client_ids:
            client = client_manager.get_client(client_id)
            if client:
                scale = client.settings.get('scale_method', 'N/A')
                status = "✅" if client.enabled else "⏸️"
                st.markdown(f"• {status} {client.name} ({scale})")
    else:
        st.warning("No clients selected for sync")

    st.markdown("---")
    st.markdown(f"**Interval:** {interval}")
    st.info("🧪 **DRY RUN MODE** - Orders will NOT be sent to Schwab")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Confirm", key="start_confirm", width='stretch'):
            st.session_state.show_start_modal = False
            
            # Записать start time для Status
            from datetime import datetime
            from app.core.json_utils import save_json
            settings['last_sync_time'] = datetime.now().isoformat()
            save_json("config/sync_settings.json", settings)
            
            # Запустить Worker
            success = start_worker()
            
            if success:
                st.session_state.copier_mode = 'AUTO'
            else:
                st.session_state.copier_mode = 'STOPPED'
            
            st.rerun()

    with col2:
        if st.button("Cancel", key="start_cancel", type="primary", width='stretch'):
            st.session_state.show_start_modal = False
            st.rerun()


@st.dialog("📊 Sync Results")
def show_sync_results_modal():
    """Модальное окно с результатами синхронизации"""
    # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
    st.session_state.show_sync_results_modal = False

    results = st.session_state.get('sync_results', {})

    if not results:
        st.info("No results")
    elif results.get('status') == 'skipped':
        reason = results.get('reason', 'unknown')
        if reason == 'outside_active_hours':
            st.warning("⏰ Sync skipped - outside active hours")
        elif reason == 'no_clients':
            st.warning("⚠️ Sync skipped - no clients selected")
        elif reason == 'main_not_authorized':
            st.error("❌ Sync failed - Main account not authorized")
        else:
            st.warning(f"⚠️ Sync skipped: {reason}")
    elif results.get('status') == 'error':
        st.error(f"❌ Sync error: {results.get('reason', 'Unknown error')}")
    else:
        st.markdown("**Results:**")
        
        total_orders = 0
        total_deltas = 0
        
        for client_id, result_data in results.items():
            if not isinstance(result_data, dict):
                continue
                
            client_name = result_data.get('client_name', client_id)
            status = result_data.get('status', 'unknown')
            
            if status == 'success':
                sync_result = result_data.get('result', {})
                deltas = sync_result.get('deltas', [])
                orders = sync_result.get('results', [])
                
                total_deltas += len(deltas)
                total_orders += len(orders)
                
                st.markdown(f"✅ **{client_name}**: {len(orders)} orders, {len(deltas)} deltas")
            else:
                error = result_data.get('error', 'Unknown error')
                st.markdown(f"❌ **{client_name}**: {error}")
        
        st.markdown("---")
        st.markdown(f"**Total:** {total_orders} orders, {total_deltas} deltas")

    st.markdown("---")
    
    if st.button("Close", key="sync_results_close", width='stretch'):
        st.session_state.show_sync_results_modal = False
        st.session_state.sync_results = {}
        st.rerun()


@st.dialog("🛑 Close All Positions")
def show_close_all_modal():
    """Модальное окно подтверждения закрытия всех позиций"""
    # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
    st.session_state.show_close_all_modal = False
    
    from app.core.json_utils import load_json
    
    # Получить режим
    settings = load_json("config/general_settings.json", default={})
    operating_mode = settings.get('operating_mode', 'monitor')
    
    # Получить список enabled клиентов
    client_manager = st.session_state.get('client_manager')
    enabled_clients = []
    if client_manager:
        enabled_clients = client_manager.get_enabled_clients()
    
    # Показать режим
    if operating_mode == 'live':
        st.error("⚠️ **LIVE MODE** — Real orders will be executed!")
    else:
        st.warning(f"🧪 **{operating_mode.upper()} MODE** — No real orders")
    
    # Показать список клиентов
    if enabled_clients:
        st.markdown("**Affected clients:**")
        for client in enabled_clients:
            st.markdown(f"• {client.name} ({client.account_number})")
    else:
        st.info("No enabled clients")
    
    st.markdown("---")
    st.markdown("This will close **ALL positions** for listed clients.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Confirm", key="close_confirm", width='stretch'):
            st.session_state.show_close_all_modal = False
            
            # ВАЖНО: Остановить Worker если работает
            from app.core.worker_client import stop_worker, is_worker_running
            if is_worker_running():
                stop_worker()
            
            st.session_state.copier_mode = 'CLOSING'
            
            # Выполнить закрытие позиций
            _execute_close_all_positions()
            
            st.session_state.copier_mode = 'STOPPED'
            st.rerun()

    with col2:
        if st.button("Cancel", key="close_cancel", type="primary", width='stretch'):
            st.session_state.show_close_all_modal = False
            st.rerun()


def _execute_close_all_positions() -> dict:
    """
    Закрыть все позиции для всех enabled клиентов.
    
    Обрабатывает:
    - Long позиции → SELL market order
    - Short позиции → BUY market order (для закрытия short)
    
    Returns:
        dict: {client_name: positions_closed_count}
    """
    from app.core.config import build_client_for_slave
    from app.gui.utils.env_manager import load_client_from_env
    from app.core.logger import logger
    from app.core.json_utils import load_json
    from app.core.sync_common import extract_order_id, get_notification_settings
    from app.core.notification_service import get_notification_service
    
    results = {}
    total_closed = 0
    client_manager = st.session_state.client_manager
    enabled_clients = client_manager.get_enabled_clients()
    
    # Проверить режим и настройки уведомлений
    settings = load_json("config/general_settings.json", default={})
    operating_mode = settings.get('operating_mode', 'monitor')
    notif_settings = get_notification_settings()
    
    for client_config in enabled_clients:
        try:
            logger.info(f"[ORDER] 🛑 Closing all positions for {client_config.name}")
            
            # Загрузить credentials
            env_data = load_client_from_env(client_config.id)
            if not env_data or not env_data.get('key_id'):
                logger.error(f"[ORDER] ❌ Credentials not found for {client_config.id}")
                results[client_config.name] = 0
                continue
            
            # Создать client
            slave_client = build_client_for_slave(
                client_config.id,
                env_data['key_id'],
                env_data['client_secret'],
                env_data['redirect_uri']
            )
            
            # Получить позиции
            account_hash = client_config.account_hash
            response = slave_client.account_details(account_hash)
            
            if response.status_code != 200:
                logger.error(f"[ORDER] ❌ Failed to get positions for {client_config.name}")
                results[client_config.name] = 0
                continue
            
            data = response.json()
            positions = data.get('securitiesAccount', {}).get('positions', [])
            
            closed_count = 0
            
            for pos in positions:
                symbol = pos.get('instrument', {}).get('symbol')
                long_qty = int(pos.get('longQuantity', 0))
                short_qty = int(pos.get('shortQuantity', 0))
                
                # Закрыть Long позиции (SELL)
                if long_qty > 0:
                    if operating_mode == 'live':
                        try:
                            from schwab.orders.equities import equity_sell_market
                            order = equity_sell_market(symbol, long_qty).build()
                            order_response = slave_client.order_place(account_hash, order)
                            
                            if order_response.status_code in [200, 201]:
                                order_id = extract_order_id(order_response)
                                logger.info(f"[ORDER]    🛑 ✅ SELL {long_qty} {symbol} (Order ID: {order_id})")
                                closed_count += 1
                            else:
                                logger.error(f"[ORDER]    🛑 ❌ Failed to SELL {symbol}: {order_response.text}")
                        except Exception as e:
                            logger.error(f"[ORDER]    🛑 ❌ Error selling {symbol}: {e}")
                    else:
                        # SIMULATION - только лог
                        logger.info(f"[ORDER]    🧪 Would SELL {long_qty} {symbol} (close long)")
                        closed_count += 1
                
                # Закрыть Short позиции (BUY to cover)
                if short_qty > 0:
                    if operating_mode == 'live':
                        try:
                            from schwab.orders.equities import equity_buy_market
                            order = equity_buy_market(symbol, short_qty).build()
                            order_response = slave_client.order_place(account_hash, order)
                            
                            if order_response.status_code in [200, 201]:
                                order_id = extract_order_id(order_response)
                                logger.info(f"[ORDER]    🛑 ✅ BUY {short_qty} {symbol} (Order ID: {order_id}) — close short")
                                closed_count += 1
                            else:
                                logger.error(f"[ORDER]    🛑 ❌ Failed to BUY (cover) {symbol}: {order_response.text}")
                        except Exception as e:
                            logger.error(f"[ORDER]    🛑 ❌ Error buying {symbol}: {e}")
                    else:
                        # SIMULATION - только лог
                        logger.info(f"[ORDER]    🧪 Would BUY {short_qty} {symbol} (close short)")
                        closed_count += 1
            
            results[client_config.name] = closed_count
            total_closed += closed_count
            logger.info(f"[ORDER] ✅ {client_config.name}: {closed_count} positions closed")
            
        except Exception as e:
            logger.error(f"[ORDER] ❌ Error closing positions for {client_config.name}: {e}")
            results[client_config.name] = 0
    
    # Toast уведомление о результатах (если toast_on_success включен)
    if notif_settings.get('toast_on_success', False) and total_closed > 0:
        notif = get_notification_service()
        mode_icon = "🛑" if operating_mode == 'live' else "🧪"
        notif.success(f"{mode_icon} Closed {total_closed} positions")
    
    st.session_state.show_close_all_modal = False
    
    return results


def reset_modal_flags():
    """Сбросить все флаги модальных окон"""
    st.session_state.show_sync_modal = False
    st.session_state.show_start_modal = False
    st.session_state.show_close_all_modal = False
    st.session_state.show_sync_results_modal = False
    st.session_state.show_exit_confirm = False
    st.session_state.show_sync_confirm = False
    st.session_state.show_start_confirm = False
