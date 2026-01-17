
# client_management.py
# app.gui.components.client_management


import streamlit as st
from app.gui.utils.env_manager import save_client_to_env
from pathlib import Path
import json
from app.gui.utils.styles import apply_tab_button_styles


def render():
    """Отрисовка Client Management"""

    st.markdown("### 👥 Clients Account Management")

    # Получить текущую вкладку
    current_tab = st.session_state.get('client_management_tab', 'General Settings')

    # CSS для голубых кнопок-вкладок
    apply_tab_button_styles()

    # Кнопки-вкладки
    col1, col2, col3 = st.columns(3)

    with col1:
        btn_type1 = "primary" if current_tab == 'General Settings' else "secondary"
        if st.button("⚙️ General Settings", type=btn_type1, width='stretch', key="client_tab_settings"):
            st.session_state.client_management_tab = 'General Settings'
            st.rerun()

    with col2:
        btn_type2 = "primary" if current_tab == 'Add New Client' else "secondary"
        if st.button("➕ Add New Client", type=btn_type2, width='stretch', key="client_tab_add"):
            st.session_state.client_management_tab = 'Add New Client'
            st.rerun()

    with col3:
        btn_type3 = "primary" if current_tab == 'Remove Client' else "secondary"
        if st.button("➖ Remove Client", type=btn_type3, width='stretch', key="client_tab_remove"):
            st.session_state.client_management_tab = 'Remove Client'
            st.rerun()

    # Отобразить контент
    if current_tab == 'General Settings':
        _render_general_settings()
    elif current_tab == 'Add New Client':
        _render_add_client()
    else:
        _render_remove_client()


def _render_general_settings():
    """Вкладка General Settings - глобальные настройки для всех клиентов"""

    from app.core.json_utils import load_json, save_json
    from pathlib import Path

    settings_file = Path("config/general_settings.json")

    # Счетчик для сброса формы
    counter = st.session_state.get('general_settings_form_counter', 0)

    # Значения по умолчанию (вложенный формат)
    defaults = {
        "operating_mode": "monitor",
        "monitor_sync_mode": "simulation",
        "trading_limits": {
            "max_order_size": 10000,
            "max_position_value": 50000,
            "min_order_value": 10,
            "max_orders_per_run": 10
        },
        "notifications": {
            "toast_on_error": True,
            "toast_on_success": False,
            "sound_on_error": True,
            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": ""
        },
        "error_handling": {
            "retry_count": 3,
            "stop_on_critical": False,
            "max_errors_per_session": 5
        }
    }
    
    # ═══════════════════════════════════════════════════════════════
    # ФУНКЦИЯ АВТОСОХРАНЕНИЯ
    # ═══════════════════════════════════════════════════════════════
    
    def _auto_save_general_settings():
        """Авто-сохранение General Settings при изменении любого виджета"""
        _settings = load_json(str(settings_file), default=defaults)
        _notif = _settings.get('notifications', {})
        
        # Получить значения из виджетов
        _max_order = st.session_state.get(f"gen_max_order_size_{counter}", 10000)
        _max_position = st.session_state.get(f"gen_max_position_value_{counter}", 50000)
        _min_order = st.session_state.get(f"gen_min_order_value_{counter}", 10)
        _max_orders = st.session_state.get(f"gen_max_orders_per_run_{counter}", 10)
        
        _toast_err = st.session_state.get(f"gen_toast_on_error_{counter}", True)
        _toast_ok = st.session_state.get(f"gen_toast_on_success_{counter}", False)
        _sound_err = st.session_state.get(f"gen_sound_on_error_{counter}", True)
        _tg_enabled = st.session_state.get(f"gen_telegram_enabled_{counter}", False)
        _tg_token = st.session_state.get(f"gen_telegram_token_{counter}", "")
        _tg_chat = st.session_state.get(f"gen_telegram_chat_id_{counter}", "")
        
        # Operating mode - ЕДИНЫЙ radio с 4 опциями
        _mode_opts = ["🔍 🔴 Monitor Live Delta", "🔍 🔶 Monitor Simulation Delta", "🔶 Simulation", "🔴 Live Mode"]
        _mode_vals = ["monitor_live", "monitor_simulation", "simulation", "live"]
        _mode_label = st.session_state.get(f"gen_operating_mode_{counter}")
        
        if _mode_label and _mode_label in _mode_opts:
            _selected = _mode_vals[_mode_opts.index(_mode_label)]
        else:
            # Восстановить из старого формата
            _old_op_mode = _settings.get('operating_mode', 'monitor')
            _old_sync_mode = _settings.get('monitor_sync_mode', 'simulation')
            if _old_op_mode == 'monitor':
                _selected = f"monitor_{_old_sync_mode}"
            else:
                _selected = _old_op_mode
        
        # Преобразовать в operating_mode и monitor_sync_mode
        if _selected == "monitor_live":
            _new_mode = "monitor"
            _monitor_sync_mode = "live"
        elif _selected == "monitor_simulation":
            _new_mode = "monitor"
            _monitor_sync_mode = "simulation"
        else:
            _new_mode = _selected
            _monitor_sync_mode = _settings.get('monitor_sync_mode', 'simulation')
        
        _old_mode = _settings.get('operating_mode', 'monitor')
        _old_monitor_sync_mode = _settings.get('monitor_sync_mode', 'simulation')
        
        # Telegram token/chat - всегда сохранять существующие данные
        # Если telegram включен И поля видны - взять из session_state
        # Иначе - сохранить старые значения из файла
        _show_tg_settings = st.session_state.get(f"show_telegram_settings_{counter}", False)
        if _tg_enabled and _show_tg_settings:
            # Поля видны - взять введённые значения
            _final_token = _tg_token if _tg_token else _notif.get('telegram_bot_token', '')
            _final_chat = _tg_chat if _tg_chat else _notif.get('telegram_chat_id', '')
        else:
            # Поля скрыты - сохранить старые значения из файла
            _final_token = _notif.get('telegram_bot_token', '')
            _final_chat = _notif.get('telegram_chat_id', '')
        
        # Если переключение на LIVE - показать модальное окно
        if _new_mode == "live" and _old_mode != "live":
            st.session_state.show_live_mode_modal = True
            st.session_state.pending_general_settings = {
                "operating_mode": _new_mode,
                "monitor_sync_mode": _monitor_sync_mode,
                "trading_limits": {
                    "max_order_size": _max_order,
                    "max_position_value": _max_position,
                    "min_order_value": _min_order,
                    "max_orders_per_run": _max_orders
                },
                "notifications": {
                    "toast_on_error": _toast_err,
                    "toast_on_success": _toast_ok,
                    "sound_on_error": _sound_err,
                    "telegram_enabled": _tg_enabled,
                    "telegram_bot_token": _final_token,
                    "telegram_chat_id": _final_chat
                },
                "error_handling": _settings.get('error_handling', defaults['error_handling'])
            }
            # Установить флаг для показа модального окна
            counter_key = 'general_settings_form_counter'
            st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
            return
        
        # Обычное сохранение
        _new_settings = {
            "operating_mode": _new_mode,
            "monitor_sync_mode": _monitor_sync_mode,
            "trading_limits": {
                "max_order_size": _max_order,
                "max_position_value": _max_position,
                "min_order_value": _min_order,
                "max_orders_per_run": _max_orders
            },
            "notifications": {
                "toast_on_error": _toast_err,
                "toast_on_success": _toast_ok,
                "sound_on_error": _sound_err,
                "telegram_enabled": _tg_enabled,
                "telegram_bot_token": _final_token,
                "telegram_chat_id": _final_chat
            },
            "error_handling": _settings.get('error_handling', defaults['error_handling'])
        }
        
        save_json(str(settings_file), _new_settings)
        
        # Перезагрузить кэш настроек (чтобы синхронизация видела новые значения)
        from app.core.config_cache import ConfigCache
        ConfigCache.reload_general_settings()
        
        # ═══════════════════════════════════════════════════════════════
        # ЛОГИКА ПЕРЕКЛЮЧЕНИЯ РЕЖИМОВ
        # ═══════════════════════════════════════════════════════════════
        
        # Случай 1: Переход на Simulation → кэш сохранён, Dashboard
        if _new_mode == 'simulation' and _old_mode != 'simulation':
            st.session_state.copier_mode = 'STOPPED'
            import streamlit.components.v1
            streamlit.components.v1.html(
                "<script>window.parent.location.reload()</script>",
                height=0
            )
            return
        
        # Случай 2: Переход на Monitor → кэш сохранён, Dashboard
        if _new_mode == 'monitor' and _old_mode != 'monitor':
            st.session_state.copier_mode = 'STOPPED'
            import streamlit.components.v1
            streamlit.components.v1.html(
                "<script>window.parent.location.reload()</script>",
                height=0
            )
            return
        
        # Случай 3: Monitor + смена опции → кэш сохранён, Dashboard
        if _new_mode == 'monitor' and _old_mode == 'monitor':
            if _monitor_sync_mode != _old_monitor_sync_mode:
                import streamlit.components.v1
                streamlit.components.v1.html(
                    "<script>window.parent.location.reload()</script>",
                    height=0
                )
                return
            # Случай 4: Monitor + нет смены опции → ничего не делать
            return

    # Загрузить текущие настройки
    current = load_json(str(settings_file), default=defaults)
    
    # Обратная совместимость: если старый плоский формат — конвертировать
    if 'trading_limits' not in current:
        current = {
            "operating_mode": current.get('operating_mode', 'simulation'),
            "trading_limits": {
                "max_order_size": current.get('MAX_ORDER_SIZE', 10000),
                "max_position_value": current.get('MAX_POSITION_VALUE', 50000),
                "min_order_value": current.get('MIN_ORDER_VALUE', 10),
                "max_orders_per_run": current.get('MAX_ORDERS_PER_RUN', 10)
            },
            "notifications": defaults['notifications'],
            "error_handling": defaults['error_handling']
        }
    
    # Обратная совместимость: добавить notifications если нет
    if 'notifications' not in current:
        current['notifications'] = defaults['notifications']
    
    # Обратная совместимость: конвертировать старый формат с simulation
    if 'simulation' in current:
        if current.get('simulation', False) and current.get('operating_mode') == 'live':
            current['operating_mode'] = 'simulation'
        del current['simulation']
    
    # Получить секции для удобства
    limits = current.get('trading_limits', defaults['trading_limits'])
    notifications = current.get('notifications', defaults['notifications'])

    # ═══════════════════════════════════════════════════════════════
    # МОДАЛЬНОЕ ОКНО ПОДТВЕРЖДЕНИЯ LIVE MODE (СНАЧАЛА!)
    # ═══════════════════════════════════════════════════════════════

    if st.session_state.get('show_live_mode_modal', False):

        st.error("### ⚠️ Switch to Live Mode")

        st.markdown("""
**Are you sure you want to enable Live Mode?**

▶️ **Warning:**
- Real orders will be placed on your brokerage account
- Real money will be used for trading
- All synchronization actions will execute actual trades

**This action requires explicit confirmation.**
        """)

        confirmed = st.checkbox(
            "I understand that Live Mode will execute real trades with real money",
            key="live_mode_confirm_checkbox"
        )

        col_confirm, col_cancel, col_space = st.columns([1, 1, 2])

        with col_confirm:
            if st.button("▶️ Enable Live Mode", type="primary", width='stretch',
                         disabled=not confirmed):
                pending = st.session_state.get('pending_general_settings', {})
                save_json(str(settings_file), pending)
                
                # Перезагрузить кэш настроек
                from app.core.config_cache import ConfigCache
                ConfigCache.reload_general_settings()

                st.session_state.copier_mode = 'STOPPED'
                st.session_state.show_live_mode_modal = False
                st.session_state.pending_general_settings = {}

                st.toast("▶️ Live Mode enabled!")
                # JavaScript reload - полная перезагрузка страницы
                import streamlit.components.v1
                streamlit.components.v1.html(
                    "<script>window.parent.location.reload()</script>",
                    height=0
                )

        with col_cancel:
            if st.button("❌ Cancel", width='stretch'):
                st.session_state.show_live_mode_modal = False
                st.session_state.pending_general_settings = {}
                st.rerun()

        return

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # ТРИ КОЛОНКИ: Trading Limits | Toast/Sound/Telegram | Operating Mode
    # ═══════════════════════════════════════════════════════════════

    col_left, col_middle, col_right = st.columns(3)

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 1: TRADING LIMITS
    # ═══════════════════════════════════════════════════════════════

    with col_left:
        st.markdown("**Trading Limits**")

        st.number_input(
            "Max Order Size (shares)",
            min_value=1,
            max_value=100000,
            value=limits.get('max_order_size', 10000),
            step=100,
            help="Maximum number of shares per single order",
            key=f"gen_max_order_size_{counter}",
            on_change=_auto_save_general_settings
        )

        st.number_input(
            "Max Position Value ($)",
            min_value=100,
            max_value=1000000,
            value=limits.get('max_position_value', 50000),
            step=1000,
            help="Maximum dollar value for any single position",
            key=f"gen_max_position_value_{counter}",
            on_change=_auto_save_general_settings
        )

        st.number_input(
            "Min Order Value ($)",
            min_value=1,
            max_value=1000,
            value=limits.get('min_order_value', 10),
            step=1,
            help="Minimum dollar value for an order to be placed",
            key=f"gen_min_order_value_{counter}",
            on_change=_auto_save_general_settings
        )

        st.number_input(
            "Max Orders Per Run",
            min_value=1,
            max_value=100,
            value=limits.get('max_orders_per_run', 10),
            step=1,
            help="Maximum number of orders per synchronization run",
            key=f"gen_max_orders_per_run_{counter}",
            on_change=_auto_save_general_settings
        )

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 2: TOAST / SOUND / TELEGRAM
    # ═══════════════════════════════════════════════════════════════

    with col_middle:
        st.markdown("**Toast**")
        
        st.checkbox(
            "Toast On Error",
            value=notifications.get('toast_on_error', True),
            key=f"gen_toast_on_error_{counter}",
            on_change=_auto_save_general_settings
        )
        
        st.checkbox(
            "Toast On Success",
            value=notifications.get('toast_on_success', False),
            key=f"gen_toast_on_success_{counter}",
            on_change=_auto_save_general_settings
        )
        
        st.markdown("**Sound**")
        
        st.checkbox(
            "Sound On Error",
            value=notifications.get('sound_on_error', True),
            key=f"gen_sound_on_error_{counter}",
            on_change=_auto_save_general_settings
        )
        
        st.markdown("**Telegram**")
        
        # Инициализация состояния для показа настроек Telegram
        if f"show_telegram_settings_{counter}" not in st.session_state:
            st.session_state[f"show_telegram_settings_{counter}"] = False
        
        # CSS для прозрачной кнопки настроек Telegram
        st.markdown("""
            <style>
                button[data-testid="stBaseButton-secondary"]:has(p:contains("📍")),
                button[data-testid="stBaseButton-secondary"]:has(p:contains("📌")) {
                    background: transparent !important;
                    border: none !important;
                    padding: 0 !important;
                    min-height: 0 !important;
                }
                div[data-testid="stHorizontalBlock"]:has(button p:contains("📍")) button,
                div[data-testid="stHorizontalBlock"]:has(button p:contains("📌")) button {
                    background: transparent !important;
                    border: none !important;
                }
            </style>
        """, unsafe_allow_html=True)
        
        # Telegram checkbox и кнопка настроек в одной строке
        tg_col1, tg_col2 = st.columns([3, 1])
        
        with tg_col1:
            telegram_enabled = st.checkbox(
                "Telegram",
                value=notifications.get('telegram_enabled', False),
                key=f"gen_telegram_enabled_{counter}",
                on_change=_auto_save_general_settings
            )
        
        with tg_col2:
            if telegram_enabled:
                # Кнопка настроек (📍 если открыто, 📌 если закрыто)
                settings_icon = "📍" if st.session_state[f"show_telegram_settings_{counter}"] else "📌"
                if st.button(settings_icon, key=f"telegram_settings_btn_{counter}", type="tertiary"):
                    st.session_state[f"show_telegram_settings_{counter}"] = not st.session_state[(f"show_telegram_set"
                                                                                                  f"tings_{counter}")]
                    st.rerun()
        
        # Показать поля Chat ID и Token если Telegram включен И нажата кнопка настроек
        if telegram_enabled and st.session_state[f"show_telegram_settings_{counter}"]:
            st.text_input(
                "Chat ID",
                value=notifications.get('telegram_chat_id', ''),
                key=f"gen_telegram_chat_id_{counter}",
                on_change=_auto_save_general_settings
            )
            
            st.text_input(
                "Bot Token",
                value=notifications.get('telegram_bot_token', ''),
                type="password",
                key=f"gen_telegram_token_{counter}",
                on_change=_auto_save_general_settings
            )

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 3: OPERATING MODE
    # ═══════════════════════════════════════════════════════════════

    with col_right:
        st.markdown("**Operating mode**")

        current_mode = current.get('operating_mode', 'monitor')
        monitor_sync_mode = current.get('monitor_sync_mode', 'simulation')

        # Единый radio с 4 опциями
        mode_options = [
            "🔍 🔴 Monitor Live Delta",
            "🔍 🔶 Monitor Simulation Delta",
            "🔶 Simulation",
            "🔴 Live Mode"
        ]

        # Определить текущий индекс
        if current_mode == 'monitor':
            if monitor_sync_mode == 'live':
                current_index = 0  # Monitor Live Delta
            else:
                current_index = 1  # Monitor Simulation Delta
        elif current_mode == 'simulation':
            current_index = 2
        elif current_mode == 'live':
            current_index = 3
        else:
            current_index = 1  # Default: Monitor Simulation Delta

        # Проверить работает ли Auto Sync
        is_auto_sync_running = st.session_state.get('copier_mode') == 'AUTO'
        
        st.radio(
            "Operating mode",
            mode_options,
            index=current_index,
            horizontal=False,
            label_visibility="collapsed",
            help="Monitor - track delta only. Simulation - full test. Live - real trading.",
            key=f"gen_operating_mode_{counter}",
            on_change=_auto_save_general_settings,
            disabled=is_auto_sync_running
        )
        
        # Подсказка для Monitor режимов
        selected_label = st.session_state.get(f"gen_operating_mode_{counter}", mode_options[current_index])
        if "Monitor" in selected_label:
            st.caption("💡 In Monitor: Sync always available")
        
        # Предупреждение если заблокировано
        if is_auto_sync_running:
            st.caption("⚠️ Stop Auto Sync to change mode")

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА RESET (слева)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    col_reset, col_spacer = st.columns([1, 3])

    with col_reset:
        if st.button("🔄 Reset to Defaults", width='stretch'):
            save_json(str(settings_file), defaults)
            
            # Перезагрузить кэш настроек
            from app.core.config_cache import ConfigCache
            ConfigCache.reload_general_settings()
            
            st.session_state.copier_mode = 'STOPPED'
            # Увеличить счетчик для сброса полей формы
            st.session_state.general_settings_form_counter = counter + 1
            # reload → Dashboard
            import streamlit.components.v1
            streamlit.components.v1.html(
                "<script>window.parent.location.reload()</script>",
                height=0
            )


def _load_general_settings() -> dict:
    """Загрузить общие настройки из файла (вложенный формат)"""
    settings_file = Path('config/general_settings.json')
    
    # Дефолтные настройки
    defaults = {
        "operating_mode": "simulation",
        "trading_limits": {
            "max_order_size": 10000,
            "max_position_value": 50000,
            "min_order_value": 10,
            "max_orders_per_run": 10
        },
        "notifications": {
            "toast_on_error": True,
            "toast_on_success": False,
            "sound_on_error": True,
            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": ""
        },
        "error_handling": {
            "retry_count": 3,
            "stop_on_critical": False,
            "max_errors_per_session": 5
        }
    }

    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
            # Обратная совместимость: конвертировать старый формат
            if 'trading_limits' not in settings:
                settings = {
                    "operating_mode": settings.get('operating_mode', 'simulation'),
                    "trading_limits": {
                        "max_order_size": settings.get('MAX_ORDER_SIZE', 10000),
                        "max_position_value": settings.get('MAX_POSITION_VALUE', 50000),
                        "min_order_value": settings.get('MIN_ORDER_VALUE', 10),
                        "max_orders_per_run": settings.get('MAX_ORDERS_PER_RUN', 10)
                    },
                    "error_handling": defaults['error_handling']
                }
            
            # Обратная совместимость: конвертировать simulation в operating_mode
            if 'simulation' in settings:
                if settings.get('simulation', False) and settings.get('operating_mode') == 'live':
                    settings['operating_mode'] = 'simulation'
                del settings['simulation']
            
            return settings
        except (json.JSONDecodeError, IOError) as e:
            st.warning(f"Could not load general settings: {e}")

    return defaults


def _save_general_settings(settings: dict):
    """Сохранить общие настройки в файл"""
    settings_file = Path('config/general_settings.json')

    # Создать директорию если не существует
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


def _render_add_client():
    """Форма добавления клиента"""

    # Используем общий счетчик для сброса форм
    counter = st.session_state.get('add_client_form_counter', 0)
    client_manager = st.session_state.client_manager

    col1, col2 = st.columns([1, 1])

    with col1:
        name_input = st.text_input(
            "Client Name *",
            placeholder="John Doe",
            key=f"new_client_name_{counter}"
        )

        account_raw = st.text_input(
            "Account Number *",
            placeholder="12345678",
            key=f"new_client_account_{counter}"
        )

        key_id_raw = st.text_input(
            "App Key (Key ID) *",
            placeholder="abc123def456ghi789",
            type="password",
            key=f"new_client_key_id_{counter}"
        )

    with col2:
        secret_raw = st.text_input(
            "App Secret (Client Secret) *",
            placeholder="xyz987uvw654rst321",
            type="password",
            key=f"new_client_secret_{counter}"
        )

        redirect_raw = st.text_input(
            "Redirect URI *",
            placeholder="https://127.0.0.1:8182",
            key=f"new_client_redirect_{counter}"
        )

    st.markdown("---")

    col_btn1, col_btn2 = st.columns([1, 3])

    with col_btn1:
        if st.button("➕ Create Client", type="primary", width='stretch'):
            if not all([name_input, account_raw, key_id_raw, secret_raw, redirect_raw]):
                st.error("⚠️ Please fill in all required fields")
            else:
                try:
                    from app.core.config import build_client_for_slave, get_hash_account
                    from app.utils.schwab_auth import authorize_client

                    client_id = f"slave_{len(client_manager.clients) + 1}"

                    # Сохранить credentials в .env
                    client_data = {
                        'name': name_input,
                        'account_number': account_raw,
                        'key_id': key_id_raw,
                        'client_secret': secret_raw,
                        'redirect_uri': redirect_raw
                    }
                    save_client_to_env(client_id, client_data)
                    
                    # Автоматическая авторизация
                    with st.spinner("Authorizing with Schwab..."):
                        auth_success = authorize_client(client_id)
                    
                    if not auth_success:
                        # Удалить credentials при неудаче
                        st.error("❌ Authorization failed! Client not created.")
                        st.info("Please check your credentials and try again.")
                        # Можно добавить удаление из .env если нужно
                        return

                    # Создать client и получить hash
                    slave_client = build_client_for_slave(
                        client_id,
                        key_id_raw,
                        secret_raw,
                        redirect_raw
                    )

                    # Получить account hash
                    account_hash = get_hash_account(slave_client, account_raw)

                    if not account_hash:
                        st.error(f"❌ Account {account_raw} not found in linked accounts")
                        st.info(
                            "Please make sure the account number is correct and the API credentials have access to it")
                    else:
                        # Использовать общие настройки как дефолт
                        general_settings = _load_general_settings()
                        limits = general_settings.get('trading_limits', {})

                        default_settings = {
                            'scale_method': 'DYNAMIC_RATIO',
                            'fixed_amount': None,
                            'threshold': 0.03,
                            'max_order_size': limits.get('max_order_size', 10000),
                            'max_position_value': limits.get('max_position_value', 50000),
                            'min_order_value': limits.get('min_order_value', 10),
                            'max_orders_per_run': limits.get('max_orders_per_run', 10),
                            'rounding_method': 'ROUND_DOWN',
                            'history_file': f'data/clients/{client_id}_history.json'
                        }

                        # Создать клиента с правильным hash
                        client_manager.add_client(
                            account_hash=account_hash,
                            account_number=account_raw,
                            name=name_input,
                            settings=default_settings
                        )

                        # Увеличить счетчик для сброса формы
                        st.session_state.add_client_form_counter = counter + 1
                        st.success(f"✅ Client '{name_input}' created and authorized!")
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error creating client: {e}")

    with col_btn2:
        if st.button("🔄 Clear", width='stretch'):
            st.session_state.add_client_form_counter = counter + 1
            st.rerun()


def _render_remove_client():
    """Форма удаления клиента"""

    client_manager = st.session_state.client_manager

    if client_manager.clients:
        client_to_remove = st.selectbox(
            "Select client to remove:",
            options=[c.id for c in client_manager.clients],
            format_func=lambda x: next(c.name for c in client_manager.clients if c.id == x),
            key="remove_client_select"
        )

        if client_to_remove:
            selected = client_manager.get_client(client_to_remove)

            st.write(f"**Name:** {selected.name}")
            st.write(f"**ID:** {selected.id}")

            st.markdown("---")

            if st.button("🗑️ Delete Client", type="primary"):
                st.session_state.show_delete_modal = True
                st.session_state.client_to_delete = client_to_remove
                st.rerun()
    else:
        st.info("No clients to remove")