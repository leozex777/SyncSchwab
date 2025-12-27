
# sidebar.py
# app.gui.components.sidebar

import streamlit as st

from app.core.json_utils import load_json
from pathlib import Path


def render():
    """Отрисовка левой панели"""

    render_control_buttons()

    st.sidebar.title("⚙️ Control Panel")

    render_navigation()

    st.sidebar.markdown("--")

    render_client_list()

    st.sidebar.markdown("--")

    # ========== LOG FILE ==========
    render_log_button()

    st.sidebar.markdown("--")

    render_close_all_button()

    render_modals()


def render_log_button():
    """Кнопка просмотра логов"""

    if st.sidebar.button("📋 Log File", use_container_width=True):
        reset_modal_flags()
        st.session_state.show_log_file = True
        st.session_state.show_main_account_edit = False
        st.session_state.show_client_management = False
        st.session_state.show_synchronization = False
        st.session_state.selected_client_id = None
        st.rerun()


def _get_operating_mode() -> str:
    """Получить текущий Operating Mode из general_settings.json"""
    settings_file = Path("config/general_settings.json")
    settings = load_json(str(settings_file), default={"operating_mode": "dry_run"})
    return settings.get("operating_mode", "dry_run")


def render_control_buttons():
    """Кнопки управления"""

    from app.gui.utils.refresh_manager import refresh_current_page

    mode = st.session_state.get('copier_mode', 'STOPPED')
    operating_mode = _get_operating_mode()

    # Иконки в зависимости от Operating Mode
    if operating_mode == "live":
        sync_icon = "▶️"
        start_icon = "▶️"
    else:
        sync_icon = "🧪"
        start_icon = "🧪"

    col1, col2, col3 = st.sidebar.columns(3)

    # ===== REFRESH =====
    with col1:
        if st.button("🔄 Refresh", key="btn_refresh", use_container_width=True):
            reset_modal_flags()
            refresh_current_page()
            st.rerun()

    # ===== SYNC (Manual Sync) =====
    with col2:
        if mode == 'STOPPED':
            if st.button(f"{sync_icon} Sync", key="btn_sync", use_container_width=True):
                reset_modal_flags()
                st.session_state.show_sync_modal = True
                st.rerun()
        elif mode == 'SYNCING':
            st.button("⏳ Sync", key="btn_sync", use_container_width=True, disabled=True)
        else:
            st.button(f"{sync_icon} Sync", key="btn_sync", use_container_width=True, disabled=True)

    # ===== START/STOP (Auto Sync) =====
    with col3:
        if mode == 'STOPPED':
            if st.button(f"{start_icon} Start", key="btn_start_stop", use_container_width=True):
                reset_modal_flags()
                st.session_state.show_start_modal = True
                st.rerun()
        elif mode == 'AUTO':
            if st.button("⏹️ Stop", key="btn_start_stop", use_container_width=True):
                reset_modal_flags()
                # Остановить Auto Sync
                from app.core.sync_service import get_sync_service
                sync_service = get_sync_service()
                sync_service.stop_auto_sync()
                st.session_state.copier_mode = 'STOPPED'
                st.rerun()
        elif mode == 'SYNCING':
            st.button("⏳ Start", key="btn_start_stop", use_container_width=True, disabled=True)
        else:
            st.button(f"{start_icon} Start", key="btn_start_stop", use_container_width=True, disabled=True)


def render_navigation():
    """Навигационные кнопки"""

    from app.gui.utils.refresh_manager import (
        navigate_to_dashboard,
        navigate_to_main_account,
        navigate_to_client_management,
        navigate_to_sync_panel
    )

    # Dashboard
    if st.sidebar.button("🏠 Dashboard", use_container_width=True):
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

    # Main Account Management
    if st.sidebar.button("🏦 Main Account Management", use_container_width=True):
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

    # Clients Account Management
    if st.sidebar.button("👥 Clients Account Management", use_container_width=True):
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

    # Sync Panel
    if st.sidebar.button("🔄 Sync Panel", use_container_width=True):
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
                    use_container_width=True
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
    """Кнопка Close all client positions"""

    mode = st.session_state.get('copier_mode', 'STOPPED')

    if mode == 'CLOSING':
        st.sidebar.button(
            "🔴 ⬜ Close all client positions",
            key="btn_close_all",
            use_container_width=True,
            disabled=True
        )
    else:
        if st.sidebar.button(
                "🔴 ▶️ Close all client positions",
                key="btn_close_all",
                use_container_width=True
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
    if st.session_state.get('show_sync_modal', False):
        show_sync_modal()

    if st.session_state.get('show_start_modal', False):
        show_start_modal()

    if st.session_state.get('show_close_all_modal', False):
        show_close_all_modal()

    if st.session_state.get('show_close_results_modal', False):
        show_close_results_modal()

    if st.session_state.get('show_sync_results_modal', False):
        show_sync_results_modal()


@st.dialog("🧪 Confirm Manual Sync (Dry Run)")
def show_sync_modal():
    """Модальное окно подтверждения ручной синхронизации"""

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
        if st.button("Confirm", key="sync_confirm", use_container_width=True):
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
        if st.button("Cancel", key="sync_cancel", type="primary", use_container_width=True):
            st.session_state.show_sync_modal = False
            st.rerun()


@st.dialog("🧪 Confirm Auto Sync (Dry Run)")
def show_start_modal():
    """Модальное окно подтверждения автоматической синхронизации"""

    from app.core.sync_service import get_sync_service
    from app.core.json_utils import load_json
    
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
        if st.button("Confirm", key="start_confirm", use_container_width=True):
            st.session_state.show_start_modal = False
            
            # Записать start time для Status
            from datetime import datetime
            from app.core.json_utils import save_json
            settings['last_sync_time'] = datetime.now().isoformat()
            save_json("config/sync_settings.json", settings)
            
            # Запустить Auto Sync
            success = sync_service.start_auto_sync()
            
            if success:
                st.session_state.copier_mode = 'AUTO'
            else:
                st.session_state.copier_mode = 'STOPPED'
            
            st.rerun()

    with col2:
        if st.button("Cancel", key="start_cancel", type="primary", use_container_width=True):
            st.session_state.show_start_modal = False
            st.rerun()


@st.dialog("📊 Sync Results")
def show_sync_results_modal():
    """Модальное окно с результатами синхронизации"""

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
    
    if st.button("Close", key="sync_results_close", use_container_width=True):
        st.session_state.show_sync_results_modal = False
        st.session_state.sync_results = {}
        st.rerun()


@st.dialog("🔴 Close All Client Positions")
def show_close_all_modal():
    """Модальное окно подтверждения закрытия всех позиций"""

    st.markdown("⚠️ **WARNING:** This will close ALL positions for these clients:")

    client_manager = st.session_state.client_manager
    enabled_clients = client_manager.get_enabled_clients()

    if enabled_clients:
        for client in enabled_clients:
            st.markdown(f"• ✅ {client.name}")
    else:
        st.warning("No enabled clients")

    st.markdown("---")
    st.warning("⚠️ This will sell ALL positions at market price!")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔴 Confirm Close All", key="close_confirm", use_container_width=True):
            st.session_state.show_close_all_modal = False
            st.session_state.copier_mode = 'CLOSING'
            
            # Выполнить закрытие позиций
            results = _execute_close_all_positions()
            
            st.session_state.close_results = results
            st.session_state.copier_mode = 'STOPPED'
            st.session_state.show_close_results_modal = True
            st.rerun()

    with col2:
        if st.button("Cancel", key="close_cancel", type="primary", use_container_width=True):
            st.session_state.show_close_all_modal = False
            st.rerun()


def _execute_close_all_positions() -> dict:
    """
    Закрыть все позиции для всех enabled клиентов.
    
    Returns:
        dict: {client_name: positions_closed_count}
    """
    from app.core.config import build_client_for_slave
    from app.gui.utils.env_manager import load_client_from_env
    from app.core.logger import logger
    from app.core.json_utils import load_json
    
    results = {}
    client_manager = st.session_state.client_manager
    enabled_clients = client_manager.get_enabled_clients()
    
    # Проверить режим
    settings = load_json("config/general_settings.json", default={})
    operating_mode = settings.get('operating_mode', 'dry_run')
    
    for client_config in enabled_clients:
        try:
            logger.info(f"🔴 Closing all positions for {client_config.name}")
            
            # Загрузить credentials
            env_data = load_client_from_env(client_config.id)
            if not env_data or not env_data.get('key_id'):
                logger.error(f"❌ Credentials not found for {client_config.id}")
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
                logger.error(f"❌ Failed to get positions for {client_config.name}")
                results[client_config.name] = 0
                continue
            
            data = response.json()
            positions = data.get('securitiesAccount', {}).get('positions', [])
            
            closed_count = 0
            
            for pos in positions:
                symbol = pos.get('instrument', {}).get('symbol')
                quantity = int(pos.get('longQuantity', 0))
                
                if quantity <= 0:
                    continue
                
                if operating_mode == 'live':
                    # LIVE - реальный ордер
                    try:
                        from schwab.orders.equities import equity_sell_market
                        order = equity_sell_market(symbol, quantity).build()
                        response = slave_client.order_place(account_hash, order)
                        
                        if response.status_code in [200, 201]:
                            logger.info(f"   🔴 ✅ SELL {quantity} {symbol}")
                            closed_count += 1
                        else:
                            logger.error(f"   🔴 ❌ Failed to sell {symbol}: {response.text}")
                    except Exception as e:
                        logger.error(f"   🔴 ❌ Error selling {symbol}: {e}")
                else:
                    # DRY RUN / SIMULATION - только лог
                    logger.info(f"   🧪 Would SELL {quantity} {symbol}")
                    closed_count += 1
            
            results[client_config.name] = closed_count
            logger.info(f"✅ {client_config.name}: {closed_count} positions closed")
            
        except Exception as e:
            logger.error(f"❌ Error closing positions for {client_config.name}: {e}")
            results[client_config.name] = 0
    
    return results


@st.dialog("📊 Close Positions Results")
def show_close_results_modal():
    """Модальное окно с результатами закрытия позиций"""

    st.markdown("**Results:**")

    results = st.session_state.get('close_results', {})

    client_manager = st.session_state.client_manager
    enabled_clients = client_manager.get_enabled_clients()

    total = 0

    if results:
        for client_name, count in results.items():
            st.markdown(f"• ✅ {client_name}: {count} positions closed")
            total += count
    else:
        for client in enabled_clients:
            st.markdown(f"• ✅ {client.name}: -- positions closed")

    st.markdown("---")

    if results:
        st.markdown(f"**Total: {total} positions closed**")
    else:
        st.markdown(f"**Total: -- positions closed**")

    st.markdown("---")

    if st.button("Close", key="results_close", use_container_width=True):
        st.session_state.show_close_results_modal = False
        st.session_state.close_results = {}
        st.rerun()


def reset_modal_flags():
    """Сбросить все флаги модальных окон"""
    st.session_state.show_sync_modal = False
    st.session_state.show_start_modal = False
    st.session_state.show_close_all_modal = False
    st.session_state.show_close_results_modal = False
    st.session_state.show_sync_results_modal = False
