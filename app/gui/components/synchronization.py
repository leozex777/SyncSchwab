
# synchronization.py
# app.gui.components.synchronization

import streamlit as st
from app.gui.utils.styles import apply_tab_button_styles
from app.core.json_utils import load_json, save_json
from pathlib import Path
from datetime import datetime


def render():
    """Отрисовка Sync Panel"""

    st.markdown("### 🔄 Synchronization")

    # Применить стили
    apply_tab_button_styles()
    
    # CSS для курсора pointer на selectbox
    st.markdown("""
        <style>
            div[data-testid="stSelectbox"] > div {
                cursor: pointer;
            }
            div[data-testid="stSelectbox"] svg {
                cursor: pointer;
            }
        </style>
    """, unsafe_allow_html=True)

    # Получить текущую вкладку (по умолчанию Auto Sync)
    current_tab = st.session_state.get('sync_panel_tab', 'Auto Sync')

    # Кнопки-вкладки
    col1, col2, col3 = st.columns(3)

    with col1:
        btn_type1 = "primary" if current_tab == 'Auto Sync' else "secondary"
        if st.button("⚙️ Auto Sync", type=btn_type1, width='stretch', key="sync_tab_auto"):
            st.session_state.sync_panel_tab = 'Auto Sync'
            st.rerun()

    with col2:
        btn_type2 = "primary" if current_tab == 'Manual Sync' else "secondary"
        if st.button("✏️ Manual Sync", type=btn_type2, width='stretch', key="sync_tab_manual"):
            st.session_state.sync_panel_tab = 'Manual Sync'
            st.rerun()

    with col3:
        btn_type3 = "primary" if current_tab == 'Optional Tab' else "secondary"
        if st.button("ℹ️ Optional Tab", type=btn_type3, width='stretch', key="sync_tab_optional"):
            st.session_state.sync_panel_tab = 'Optional Tab'
            st.rerun()

    st.markdown("---")

    # Отобразить контент
    if current_tab == 'Auto Sync':
        _render_auto_sync()
    elif current_tab == 'Manual Sync':
        _render_manual_sync()
    else:
        _render_optional_tab()


def _get_sync_settings_file() -> Path:
    """Путь к файлу настроек синхронизации"""
    return Path("config/sync_settings.json")


def _get_sync_defaults() -> dict:
    """Настройки по умолчанию"""
    return {
        # Auto Sync
        "auto_sync_all_enabled": True,
        "auto_selected_clients": [],
        "auto_sync_interval": "Every 5 minutes",
        "auto_sync_market_hours": True,
        "auto_sync_start_time": "09:30",
        "auto_sync_end_time": "16:00",
        # Manual Sync
        "sync_all_enabled": True,
        "selected_clients": [],
        # Status (runtime data)
        "last_sync_time": None,
        "syncs_today": 0,
        "syncs_today_date": None
    }


def _load_sync_settings() -> dict:
    """Загрузить настройки синхронизации"""
    settings_file = _get_sync_settings_file()
    return load_json(str(settings_file), default=_get_sync_defaults())


def _save_sync_settings(settings: dict):
    """Сохранить настройки синхронизации"""
    settings_file = _get_sync_settings_file()
    save_json(str(settings_file), settings)


# ═══════════════════════════════════════════════════════════════
# АВТОСОХРАНЕНИЕ НАСТРОЕК
# ═══════════════════════════════════════════════════════════════

def _auto_save_auto_sync():
    """Авто сохранение настроек Auto Sync при изменении любого виджета"""
    counter = st.session_state.get('sync_form_counter', 0)
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    all_clients = client_manager.clients
    
    # Получить значения из виджетов
    sync_mode = st.session_state.get(f"auto_sync_mode_radio_{counter}")
    enable_all = (sync_mode == "Enable Automatic Sync") if sync_mode else True
    
    # Собрать выбранных клиентов
    selected_clients = []
    if not enable_all:
        for client in all_clients:
            if st.session_state.get(f"auto_client_{client.id}_{counter}", False):
                selected_clients.append(client.id)
    
    # Получить интервал
    interval = st.session_state.get(f"auto_interval_{counter}", settings.get('auto_sync_interval', 'Every 5 minutes'))
    
    # Получить market hours
    market_hours = st.session_state.get(f"auto_market_hours_{counter}", True)
    
    # Обновить настройки
    settings['auto_sync_all_enabled'] = enable_all
    settings['auto_selected_clients'] = selected_clients if not enable_all else []
    settings['auto_sync_interval'] = interval
    settings['auto_sync_market_hours'] = market_hours
    
    # Получить время если не market hours, иначе сбросить на дефолтные
    if not market_hours:
        start_time = st.session_state.get(f"auto_start_time_{counter}")
        end_time = st.session_state.get(f"auto_end_time_{counter}")
        if start_time:
            settings['auto_sync_start_time'] = start_time.strftime("%H:%M")
        if end_time:
            settings['auto_sync_end_time'] = end_time.strftime("%H:%M")
    else:
        # Market Hours активен — сбросить на дефолтные значения
        settings['auto_sync_start_time'] = "09:30"
        settings['auto_sync_end_time'] = "16:00"
    
    _save_sync_settings(settings)


def _auto_save_manual_sync():
    """Авто сохранение настроек Manual Sync при изменении любого виджета"""
    counter = st.session_state.get('sync_form_counter', 0)
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    all_clients = client_manager.clients
    
    # Получить значения из виджетов
    sync_mode = st.session_state.get(f"manual_sync_mode_radio_{counter}")
    sync_all = (sync_mode == "Enable Automatic Sync") if sync_mode else True
    
    # Собрать выбранных клиентов
    selected_clients = []
    if not sync_all:
        for client in all_clients:
            if st.session_state.get(f"manual_client_{client.id}_{counter}", False):
                selected_clients.append(client.id)
    
    # Обновить настройки
    settings['sync_all_enabled'] = sync_all
    settings['selected_clients'] = selected_clients if not sync_all else []
    
    _save_sync_settings(settings)


def _get_interval_minutes(interval_str: str) -> int:
    """Получить интервал в минутах из строки"""
    intervals = {
        "Every 1 minute": 1,
        "Every 5 minutes": 5,
        "Every 15 minutes": 15,
        "Every 30 minutes": 30,
        "Every hour": 60
    }
    return intervals.get(interval_str, 5)


def _calculate_next_sync(next_sync_time: str, interval_str: str) -> str:
    """Рассчитать время до следующей синхронизации"""
    if not next_sync_time:
        # Нет данных — показать интервал
        interval_minutes = _get_interval_minutes(interval_str)
        return f"{interval_minutes} min 0 sec"
    
    try:
        next_sync = datetime.fromisoformat(next_sync_time)
        now = datetime.now()
        
        # Сколько секунд осталось
        remaining = (next_sync - now).total_seconds()
        
        # Если время прошло — показать интервал (sync скоро будет)
        if remaining < 0:
            interval_minutes = _get_interval_minutes(interval_str)
            interval_seconds = interval_minutes * 60
            # Рассчитать сколько осталось до следующего цикла
            remaining = interval_seconds - (abs(remaining) % interval_seconds)
        
        minutes = int(remaining) // 60
        seconds = int(remaining) % 60
        
        if minutes > 0:
            return f"{minutes} min {seconds} sec"
        else:
            return f"{seconds} sec"
            
    except (ValueError, TypeError):
        interval_minutes = _get_interval_minutes(interval_str)
        return f"{interval_minutes} min 0 sec"


def _format_last_sync_time(last_sync_time: str) -> str:
    """Форматировать время последней синхронизации"""
    if not last_sync_time:
        return "--"
    
    try:
        last_sync = datetime.fromisoformat(last_sync_time)
        return last_sync.strftime("%I:%M %p")
    except (ValueError, TypeError):
        return "--"


def _render_auto_sync():
    """Автоматическая синхронизация по расписанию"""

    # Счетчик для сброса формы
    counter = st.session_state.get('sync_form_counter', 0)

    # Загрузить настройки
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    all_clients = client_manager.clients
    enabled_clients = client_manager.get_enabled_clients()

    # Проверить режим работы
    copier_mode = st.session_state.get('copier_mode', 'STOPPED')
    is_running = copier_mode == 'AUTO'

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    # ТРИ КОЛОНКИ
    # ═══════════════════════════════════════════════════════════════

    col_left, col_middle, col_right = st.columns(3)

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 1: Выбор клиентов (Radio-style через session_state)
    # ═══════════════════════════════════════════════════════════════

    with col_left:
        # Radio вместо двух checkbox
        sync_mode = st.radio(
            "Client Selection",
            options=["Enable Automatic Sync", "Select Client Automatic Sync"],
            index=0 if settings.get('auto_sync_all_enabled', True) else 1,
            key=f"auto_sync_mode_radio_{counter}",
            label_visibility="collapsed",
            on_change=_auto_save_auto_sync
        )

        enable_all = (sync_mode == "Enable Automatic Sync")

        # Список клиентов или info
        if enable_all:
            # Текст без голубого фона
            st.markdown(f"✅ All {len(enabled_clients)} clients selected")
        else:
            # Список клиентов с информацией о статусе в одной строке
            st.markdown("")
            saved_selected = settings.get('auto_selected_clients', [])

            for client in all_clients:
                is_selected = client.id in saved_selected
                status_icon = "✅" if client.enabled else "⏸️"
                status_text = "Active" if client.enabled else "Inactive"

                st.checkbox(
                    f"{client.name} ({status_icon} {status_text})",
                    value=is_selected,
                    key=f"auto_client_{client.id}_{counter}",
                    on_change=_auto_save_auto_sync
                )

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 2: Sync Interval + Status
    # ═══════════════════════════════════════════════════════════════

    with col_middle:
        # Sync Interval
        st.markdown("**Sync Interval**")

        intervals = [
            "Every 1 minute",
            "Every 5 minutes",
            "Every 15 minutes",
            "Every 30 minutes",
            "Every hour"
        ]
        current_interval = settings.get('auto_sync_interval', 'Every 5 minutes')
        interval_index = intervals.index(current_interval) if current_interval in intervals else 1

        # Блокировать selectbox если AUTO режим
        if is_running:
            # Показать предупреждение и заблокированный selectbox
            st.selectbox(
                "Sync Interval",
                intervals,
                index=interval_index,
                key=f"auto_interval_{counter}",
                label_visibility="collapsed",
                disabled=True
            )
            st.caption("⚠️ Stop Auto Sync to change interval")
        else:
            st.selectbox(
                "Sync Interval",
                intervals,
                index=interval_index,
                key=f"auto_interval_{counter}",
                label_visibility="collapsed",
                on_change=_auto_save_auto_sync
            )

        st.markdown("")

        # ═══════════════════════════════════════════════════════════════
        # STATUS BLOCK (с fragment для автообновления)
        # ═══════════════════════════════════════════════════════════════
        
        # Заголовок Status
        st.caption("Status (updates every 1 sec)")
        
        # Fragment для автообновления Status
        _render_status_fragment()

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 3: Active Hours (Market Hours)
    # ═══════════════════════════════════════════════════════════════

    with col_right:
        st.markdown("**Active Hours (Market Hours):**")

        market_hours = st.checkbox(
            "Only during market hours (9:30 AM - 4:00 PM ET)",
            value=settings.get('auto_sync_market_hours', True),
            key=f"auto_market_hours_{counter}",
            on_change=_auto_save_auto_sync
        )

        # Если снять галочку - показать Start Time / End Time
        if not market_hours:
            st.markdown("")

            saved_start = settings.get('auto_sync_start_time', '09:30')
            saved_end = settings.get('auto_sync_end_time', '16:00')

            try:
                start_time_value = datetime.strptime(saved_start, "%H:%M").time()
            except (ValueError, TypeError):
                start_time_value = datetime.strptime("09:30", "%H:%M").time()

            try:
                end_time_value = datetime.strptime(saved_end, "%H:%M").time()
            except (ValueError, TypeError):
                end_time_value = datetime.strptime("16:00", "%H:%M").time()

            st.time_input(
                "Start Time",
                value=start_time_value,
                key=f"auto_start_time_{counter}",
                on_change=_auto_save_auto_sync
            )

            st.time_input(
                "End Time",
                value=end_time_value,
                key=f"auto_end_time_{counter}",
                on_change=_auto_save_auto_sync
            )

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА RESET (слева)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    col_reset, col_spacer = st.columns([1, 3])

    with col_reset:
        if st.button("🔄 Reset to Defaults", width='stretch', key="auto_reset_btn"):
            # Загрузить текущие настройки
            current_settings = _load_sync_settings()
            defaults = _get_sync_defaults()

            # Сбросить ТОЛЬКО Auto Sync настройки
            current_settings['auto_sync_all_enabled'] = defaults['auto_sync_all_enabled']
            current_settings['auto_selected_clients'] = defaults['auto_selected_clients']
            current_settings['auto_sync_interval'] = defaults['auto_sync_interval']
            current_settings['auto_sync_market_hours'] = defaults['auto_sync_market_hours']
            current_settings['auto_sync_start_time'] = defaults['auto_sync_start_time']
            current_settings['auto_sync_end_time'] = defaults['auto_sync_end_time']

            # НЕ трогать Manual Sync и runtime данные

            _save_sync_settings(current_settings)
            st.session_state.sync_form_counter = counter + 1
            st.toast("✅ Auto Sync reset to defaults!")
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# FRAGMENT ДЛЯ АВТООБНОВЛЕНИЯ STATUS
# ═══════════════════════════════════════════════════════════════

@st.fragment(run_every=1)
def _render_status_fragment():
    """
    Fragment для автообновления Status блока.
    Обновляется каждую секунду независимо от остальной страницы.
    """
    import json

    # Читать sync_settings.json
    try:
        with open("config/sync_settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = _get_sync_defaults()

    # Читать worker_status.json для определения is_running
    try:
        with open("config/worker_status.json", "r", encoding="utf-8") as f:
            worker_status = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        worker_status = {}
    
    # Worker running если command=start И running=True
    is_running = (
        worker_status.get("command") == "start" and 
        worker_status.get("running", False)
    )

    # Получить данные
    last_sync_time = settings.get('last_sync_time')
    next_sync_time = settings.get('next_sync_time')
    syncs_today = settings.get('syncs_today', 0)
    current_interval = settings.get('auto_sync_interval', 'Every 5 minutes')
    interval_minutes = _get_interval_minutes(current_interval)

    # Сбросить счетчик если новый день
    syncs_today_date = settings.get('syncs_today_date')
    today_str = datetime.now().strftime("%Y-%m-%d")
    if syncs_today_date != today_str:
        syncs_today = 0

    # Отобразить Status
    col_label, col_value = st.columns([1, 1])

    with col_label:
        st.markdown("Last Sync")
        st.markdown("Next Sync In")
        st.markdown("Syncs Today")

    with col_value:
        if is_running:
            # AUTO режим - показывать реальные значения из файла
            st.markdown(f"**{_format_last_sync_time(last_sync_time)}**")
            st.markdown(f"**{_calculate_next_sync(next_sync_time, current_interval)}**")
            st.markdown(f"**{syncs_today}**")
        else:
            # STOPPED режим
            st.markdown("**--**")
            st.markdown(f"**{interval_minutes:02d}:00**")
            st.markdown(f"**{syncs_today}**")


def _render_manual_sync():
    """Ручная синхронизация"""

    # Счетчик для сброса формы
    counter = st.session_state.get('sync_form_counter', 0)

    # Загрузить настройки
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    all_clients = client_manager.clients
    enabled_clients = client_manager.get_enabled_clients()

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    # Radio-style выбор клиентов
    # ═══════════════════════════════════════════════════════════════

    sync_mode = st.radio(
        "Client Selection",
        options=["Enable Automatic Sync", "Select Client Automatic Sync"],
        index=0 if settings.get('sync_all_enabled', True) else 1,
        key=f"manual_sync_mode_radio_{counter}",
        label_visibility="collapsed",
        on_change=_auto_save_manual_sync
    )

    sync_all = (sync_mode == "Enable Automatic Sync")

    # Список клиентов или info
    if sync_all:
        # Текст без голубого фона
        st.markdown(f"✅ All {len(enabled_clients)} clients selected")
    else:
        # Список клиентов с информацией о статусе
        st.markdown("")
        saved_selected = settings.get('selected_clients', [])

        for client in all_clients:
            is_selected = client.id in saved_selected
            status_icon = "✅" if client.enabled else "⏸️"
            status_text = "Active" if client.enabled else "Inactive"

            st.checkbox(
                f"{client.name} ({status_icon} {status_text})",
                value=is_selected,
                key=f"manual_client_{client.id}_{counter}",
                on_change=_auto_save_manual_sync
            )

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА RESET (слева)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    col_reset, col_spacer = st.columns([1, 3])

    with col_reset:
        if st.button("🔄 Reset to Defaults", width='stretch', key="manual_reset_btn"):
            # Загрузить текущие настройки
            current_settings = _load_sync_settings()
            defaults = _get_sync_defaults()

            # Сбросить ТОЛЬКО Manual Sync настройки
            current_settings['sync_all_enabled'] = defaults['sync_all_enabled']
            current_settings['selected_clients'] = defaults['selected_clients']

            # НЕ трогать Auto Sync и runtime данные

            _save_sync_settings(current_settings)
            st.session_state.sync_form_counter = counter + 1
            st.toast("✅ Manual Sync reset to defaults!")
            st.rerun()


def _render_optional_tab():
    """Опциональная вкладка (для тестирования или будущего использования)"""

    st.markdown("**Optional Tab**")
    st.info("This tab is reserved for future functionality or testing.")

    # Можно добавить сюда любой контент:
    # - Логи синхронизации
    # - Статистика
    # - Расширенные настройки
    # - Тестовые функции


# ═══════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ИНТЕГРАЦИИ С SIDEBAR
# ═══════════════════════════════════════════════════════════════

def get_auto_sync_clients() -> list:
    """Получить список клиентов для Auto Sync (для кнопки Start)"""
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    
    if settings.get('auto_sync_all_enabled', True):
        # Все enabled клиенты
        return [c.id for c in client_manager.get_enabled_clients()]
    else:
        # Выбранные клиенты
        return settings.get('auto_selected_clients', [])


def get_manual_sync_clients() -> list:
    """Получить список клиентов для Manual Sync (для кнопки Sync)"""
    settings = _load_sync_settings()
    client_manager = st.session_state.client_manager
    
    if settings.get('sync_all_enabled', True):
        # Все enabled клиенты
        return [c.id for c in client_manager.get_enabled_clients()]
    else:
        # Выбранные клиенты
        return settings.get('selected_clients', [])


def get_auto_sync_interval_seconds() -> int:
    """Получить интервал Auto Sync в секундах"""
    settings = _load_sync_settings()
    interval_str = settings.get('auto_sync_interval', 'Every 5 minutes')
    return _get_interval_minutes(interval_str) * 60


def update_sync_status(last_sync_time: str = None):
    """Обновить статус синхронизации после выполнения"""
    settings = _load_sync_settings()
    
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    # Обновить время последней синхронизации
    if last_sync_time:
        settings['last_sync_time'] = last_sync_time
    else:
        settings['last_sync_time'] = now.isoformat()
    
    # Обновить счетчик за день
    if settings.get('syncs_today_date') != today_str:
        settings['syncs_today'] = 1
        settings['syncs_today_date'] = today_str
    else:
        settings['syncs_today'] = settings.get('syncs_today', 0) + 1
    
    _save_sync_settings(settings)


def is_within_active_hours() -> bool:
    """Проверить находимся ли в активных часах"""
    settings = _load_sync_settings()
    
    if settings.get('auto_sync_market_hours', True):
        # Market hours: 9:30 AM - 4:00 PM ET
        # TODO: Добавить timezone conversion
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now <= market_close
    else:
        # Custom hours
        start_str = settings.get('auto_sync_start_time', '09:30')
        end_str = settings.get('auto_sync_end_time', '16:00')
        
        try:
            now = datetime.now()
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            
            return start_time <= now.time() <= end_time
        except (ValueError, TypeError):
            return True  # Default to active if parsing fails
