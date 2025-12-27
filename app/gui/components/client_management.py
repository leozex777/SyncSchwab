
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
        if st.button("⚙️ General Settings", type=btn_type1, use_container_width=True, key="client_tab_settings"):
            st.session_state.client_management_tab = 'General Settings'
            st.rerun()

    with col2:
        btn_type2 = "primary" if current_tab == 'Add New Client' else "secondary"
        if st.button("➕ Add New Client", type=btn_type2, use_container_width=True, key="client_tab_add"):
            st.session_state.client_management_tab = 'Add New Client'
            st.rerun()

    with col3:
        btn_type3 = "primary" if current_tab == 'Remove Client' else "secondary"
        if st.button("➖ Remove Client", type=btn_type3, use_container_width=True, key="client_tab_remove"):
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
            if st.button("▶️ Enable Live Mode", type="primary", use_container_width=True,
                         disabled=not confirmed):
                pending = st.session_state.get('pending_general_settings', {})
                save_json(str(settings_file), pending)

                st.session_state.copier_mode = 'STOPPED'
                st.session_state.show_live_mode_modal = False
                st.session_state.pending_general_settings = {}

                st.toast("▶️ Live Mode enabled!")
                st.rerun()

        with col_cancel:
            if st.button("❌ Cancel", use_container_width=True):
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

        max_order_size = st.number_input(
            "Max Order Size (shares)",
            min_value=1,
            max_value=100000,
            value=limits.get('max_order_size', 10000),
            step=100,
            help="Maximum number of shares per single order",
            key=f"gen_max_order_size_{counter}"
        )

        max_position_value = st.number_input(
            "Max Position Value ($)",
            min_value=100,
            max_value=1000000,
            value=limits.get('max_position_value', 50000),
            step=1000,
            help="Maximum dollar value for any single position",
            key=f"gen_max_position_value_{counter}"
        )

        min_order_value = st.number_input(
            "Min Order Value ($)",
            min_value=1,
            max_value=1000,
            value=limits.get('min_order_value', 10),
            step=1,
            help="Minimum dollar value for an order to be placed",
            key=f"gen_min_order_value_{counter}"
        )

        max_orders_per_run = st.number_input(
            "Max Orders Per Run",
            min_value=1,
            max_value=100,
            value=limits.get('max_orders_per_run', 10),
            step=1,
            help="Maximum number of orders per synchronization run",
            key=f"gen_max_orders_per_run_{counter}"
        )

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 2: TOAST / SOUND / TELEGRAM
    # ═══════════════════════════════════════════════════════════════

    with col_middle:
        st.markdown("**Toast**")
        
        toast_on_error = st.checkbox(
            "Toast On Error",
            value=notifications.get('toast_on_error', True),
            key=f"gen_toast_on_error_{counter}"
        )
        
        toast_on_success = st.checkbox(
            "Toast On Success",
            value=notifications.get('toast_on_success', False),
            key=f"gen_toast_on_success_{counter}"
        )
        
        st.markdown("**Sound**")
        
        sound_on_error = st.checkbox(
            "Sound On Error",
            value=notifications.get('sound_on_error', True),
            key=f"gen_sound_on_error_{counter}"
        )
        
        st.markdown("**Telegram**")
        
        telegram_enabled = st.checkbox(
            "Telegram (заглушка)",
            value=notifications.get('telegram_enabled', False),
            key=f"gen_telegram_enabled_{counter}"
        )
        
        # Показать поля Token и Chat ID если Telegram включен
        if telegram_enabled:
            telegram_bot_token = st.text_input(
                "Bot Token",
                value=notifications.get('telegram_bot_token', ''),
                type="password",
                key=f"gen_telegram_token_{counter}"
            )
            
            telegram_chat_id = st.text_input(
                "Chat ID",
                value=notifications.get('telegram_chat_id', ''),
                key=f"gen_telegram_chat_id_{counter}"
            )
        else:
            telegram_bot_token = notifications.get('telegram_bot_token', '')
            telegram_chat_id = notifications.get('telegram_chat_id', '')

    # ═══════════════════════════════════════════════════════════════
    # КОЛОНКА 3: OPERATING MODE
    # ═══════════════════════════════════════════════════════════════

    with col_right:
        st.markdown("**Operating mode**")

        current_mode = current.get('operating_mode', 'simulation')

        mode_options = ["▶️ Live Mode", "🔶 Simulation Live", "🧪 Dry Run (Test)"]
        mode_values = ["live", "simulation", "dry_run"]

        current_index = mode_values.index(current_mode) if current_mode in mode_values else 1

        selected_mode_label = st.radio(
            "Operating mode",
            mode_options,
            index=current_index,
            horizontal=False,
            label_visibility="collapsed",
            help="Dry Run - quick test. Simulation Live - full test without orders. Live Mode - real trading.",
            key=f"gen_operating_mode_{counter}"
        )

        selected_mode = mode_values[mode_options.index(selected_mode_label)]

    # ═══════════════════════════════════════════════════════════════
    # КНОПКИ SAVE / RESET (по центру)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    col_spacer1, col_save, col_reset, col_spacer2 = st.columns([1, 1, 1, 1])

    with col_save:
        if st.button("💾 Save General Settings", type="primary", use_container_width=True):
            # Показать модальное окно только при переключении на LIVE
            if selected_mode == "live" and current_mode != "live":
                st.session_state.show_live_mode_modal = True
                st.session_state.pending_general_settings = {
                    "operating_mode": selected_mode,
                    "trading_limits": {
                        "max_order_size": max_order_size,
                        "max_position_value": max_position_value,
                        "min_order_value": min_order_value,
                        "max_orders_per_run": max_orders_per_run
                    },
                    "notifications": {
                        "toast_on_error": toast_on_error,
                        "toast_on_success": toast_on_success,
                        "sound_on_error": sound_on_error,
                        "telegram_enabled": telegram_enabled,
                        "telegram_bot_token": telegram_bot_token,
                        "telegram_chat_id": telegram_chat_id
                    },
                    "error_handling": current.get('error_handling', defaults['error_handling'])
                }
                st.rerun()
            else:
                new_settings = {
                    "operating_mode": selected_mode,
                    "trading_limits": {
                        "max_order_size": max_order_size,
                        "max_position_value": max_position_value,
                        "min_order_value": min_order_value,
                        "max_orders_per_run": max_orders_per_run
                    },
                    "notifications": {
                        "toast_on_error": toast_on_error,
                        "toast_on_success": toast_on_success,
                        "sound_on_error": sound_on_error,
                        "telegram_enabled": telegram_enabled,
                        "telegram_bot_token": telegram_bot_token,
                        "telegram_chat_id": telegram_chat_id
                    },
                    "error_handling": current.get('error_handling', defaults['error_handling'])
                }
                save_json(str(settings_file), new_settings)

                if selected_mode != current_mode:
                    st.session_state.copier_mode = 'STOPPED'

                st.toast("✅ Settings saved!")
                st.rerun()

    with col_reset:
        if st.button("🔄 Reset to Defaults", use_container_width=True):
            save_json(str(settings_file), defaults)
            st.session_state.copier_mode = 'STOPPED'
            # Увеличить счетчик для сброса полей формы
            st.session_state.general_settings_form_counter = counter + 1
            st.toast("✅ Reset to defaults!")
            st.rerun()


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
        if st.button("➕ Create Client", type="primary", use_container_width=True):
            if not all([name_input, account_raw, key_id_raw, secret_raw, redirect_raw]):
                st.error("⚠️ Please fill in all required fields")
            else:
                try:
                    from app.core.config import build_client_for_slave, get_hash_account

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
                        st.success(f"✅ Client '{name_input}' added successfully!")
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error creating client: {e}")

    with col_btn2:
        if st.button("🔄 Clear", use_container_width=True):
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