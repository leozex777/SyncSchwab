
# dashboard.py
# app.gui.components.dashboard

import streamlit as st
from typing import Dict, List

from app.core.token_checker import check_all_tokens
from app.utils.schwab_auth import authorize_main_account, authorize_client
from app.core.json_utils import load_json, save_json
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path

load_dotenv()


# ═══════════════════════════════════════════════════════════════
# EXPANDER STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def _get_ui_state_file() -> Path:
    """Путь к файлу состояния UI"""
    return Path("config/ui_state.json")


def _load_expander_states() -> dict:
    """Загрузить состояния всех expanders"""
    return load_json(str(_get_ui_state_file()), default={"dashboard_expanders": {}})


def _save_expander_state(expander_id: str, is_pinned: bool):
    """Сохранить состояние expander"""
    state = _load_expander_states()
    if "dashboard_expanders" not in state:
        state["dashboard_expanders"] = {}
    state["dashboard_expanders"][expander_id] = is_pinned
    save_json(str(_get_ui_state_file()), state)


def _is_expander_pinned(expander_id: str, default: bool = False) -> bool:
    """Проверить закреплен ли expander"""
    state = _load_expander_states()
    return state.get("dashboard_expanders", {}).get(expander_id, default)


def _render_pin_checkbox(expander_id: str):
    """Отрисовать checkbox Pin слева вверху внутри expander"""
    is_pinned = _is_expander_pinned(expander_id)

    icon = "📍" if is_pinned else "📌"

    new_pinned = st.checkbox(
        icon,
        value=is_pinned,
        key=f"pin_cb_{expander_id}",
        help="Keep this section open"
    )

    if new_pinned != is_pinned:
        _save_expander_state(expander_id, new_pinned)
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# AUTH HELPERS
# ═══════════════════════════════════════════════════════════════

def is_sunday() -> bool:
    """Проверить что сегодня воскресенье"""
    return datetime.now().weekday() == 6


def was_authorized_today(token_file_path: str) -> bool:
    """
    Проверить была ли авторизация сегодня.
    Смотрим на refresh_token_issued в файле токена.
    """
    import json

    token_file = Path(token_file_path)

    if not token_file.exists():
        return False

    try:
        with open(token_file, 'r') as f:
            tokens = json.load(f)

        refresh_issued = tokens.get('refresh_token_issued', '')

        if not refresh_issued:
            return False

        # Парсим дату
        issued_date = datetime.fromisoformat(refresh_issued)
        today = datetime.now(timezone.utc).date()

        return issued_date.date() == today

    except (OSError, IOError, json.JSONDecodeError, ValueError, KeyError, TypeError):
        return False


def should_show_auth_button(token_valid: bool, token_file_path: str = None) -> bool:
    """
    Определить нужно ли показывать кнопку Auth
    """
    if not token_valid:
        return True

    if is_sunday():
        if token_file_path and was_authorized_today(token_file_path):
            return False
        return True

    return False


# ═══════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════

def render():
    """Главная страница Dashboard"""

    from app.core.cache_manager import ensure_cache_loaded

    # Загрузить кэш при первом запуске
    ensure_cache_loaded()

    # CSS
    st.markdown("""
    <style>
    .block-container { 
        padding-top: 2rem;
        padding-bottom: 1rem; 
    }
    .stMetric { font-size: 0.85rem; }
    .stMetric label { font-size: 0.75rem !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    div[data-testid="stExpander"] { font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════
    render_quick_actions()

    # Получить статус всех токенов
    client_manager = st.session_state.client_manager
    status = check_all_tokens(client_manager)

    # ═══════════════════════════════════════════════════
    # 1️⃣ MAIN ACCOUNT
    # ═══════════════════════════════════════════════════
    render_main_account_section(status['main'])

    # ═══════════════════════════════════════════════════
    # 2️⃣ CLIENTS
    # ═══════════════════════════════════════════════════
    render_clients_section(status['clients'], client_manager)

    # ═══════════════════════════════════════════════════
    # 6️⃣ POSITION COMPARISON
    # ═══════════════════════════════════════════════════
    render_position_comparison(status['main'], client_manager)

    # ═══════════════════════════════════════════════════
    # 5️⃣ SYNC HISTORY
    # ═══════════════════════════════════════════════════
    render_sync_history()

    st.markdown("---")

    # ═══════════════════════════════════════════════════
    # 3️⃣ MARKET STATUS
    # ═══════════════════════════════════════════════════
    render_market_status()

    # ═══════════════════════════════════════════════════
    # 4️⃣ SCHWAB API STATUS
    # ═══════════════════════════════════════════════════
    render_api_status(status['main'])


# ═══════════════════════════════════════════════════════════════
# QUICK ACTIONS
# ═══════════════════════════════════════════════════════════════

def render_quick_actions():
    """Заголовок страницы"""
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🚀 Multi-Client Position Copier")


# ═══════════════════════════════════════════════════════════════
# 1️⃣ MAIN ACCOUNT
# ═══════════════════════════════════════════════════════════════

def render_main_account_section(main_status: Dict):
    """Секция Main Account - компактная"""

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        if main_status['credentials_ok']:
            st.markdown(
                "✅ <span style='font-size: 1.5rem; font-weight: 600;'>🏦 Main Account</span>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "❌ <span style='font-size: 1.5rem; font-weight: 600;'>🏦 Main Account</span>",
                unsafe_allow_html=True
            )
            st.caption("Add credentials to .env file")
            return

    with col2:
        if main_status['is_valid']:
            st.markdown(f"✅ Token: {main_status['message'].replace('✅ ', '')}")
        else:
            st.markdown("❌ Token Invalid")

    with col3:
        from app.core.paths import TOKEN_PATH
        token_file = str(TOKEN_PATH / "main_tokens.json")

        if should_show_auth_button(main_status['is_valid'], token_file) and main_status['credentials_ok']:

            if 'auth_errors' not in st.session_state:
                st.session_state.auth_errors = {}

            has_error = st.session_state.auth_errors.get('main', False)

            btn_icon = "⚠️" if has_error else "🔐"
            btn_help = "Authorization failed. Retry?" if has_error else (
                "Authorization required" if not main_status['is_valid'] else "Weekly token refresh"
            )

            if st.button(f"{btn_icon} Auth", key="auth_main_btn", type="primary", help=btn_help):
                with st.spinner("Authorizing..."):
                    success = authorize_main_account()
                    st.session_state.auth_errors['main'] = not success
                    st.rerun()

    if main_status['is_valid']:
        render_main_account_info()


def render_main_account_info():
    """Краткая информация о Main Account (из кэша)"""

    from app.core.cache_manager import get_cached_main_account, ensure_cache_loaded

    ensure_cache_loaded()
    cached = get_cached_main_account()

    if not cached:
        st.caption("⚠️ No account data. Click Refresh.")
        return

    account_number = cached.get('account_number', '')
    balances = cached.get('balances', {})
    positions = cached.get('positions', [])
    total_pl = cached.get('total_pl', 0)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Account", f"****{account_number[-4:]}" if account_number else "N/A")

    with col2:
        total_value = balances.get('liquidation_value', 0)
        st.metric("Total", f"${total_value:,.0f}")

    with col3:
        cash = balances.get('cash_balance', 0)
        st.metric("Cash", f"${cash:,.0f}")

    with col4:
        st.metric("Positions", len(positions))

    with col5:
        st.metric("P&L", f"${total_pl:+,.0f}")


# ═══════════════════════════════════════════════════════════════
# 2️⃣ CLIENTS
# ═══════════════════════════════════════════════════════════════

def render_clients_section(clients_status: List[Dict], client_manager):
    """Секция клиентов"""

    if not clients_status:
        st.info("No clients configured. Go to **Client Management** to add clients.")
        return

    for client_status in clients_status:
        render_client_row(client_status, client_manager)


def render_client_row(client_status: Dict, client_manager):
    """Одна строка клиента"""

    client_id = client_status['client_id']
    client_name = client_status['client_name']
    is_valid = client_status['is_valid']
    credentials_ok = client_status['credentials_ok']
    message = client_status.get('message', '')
    is_enabled = client_status.get('is_enabled', True)

    client_config = client_manager.get_client(client_id)
    status_icon = "✅" if is_enabled else "❌"

    if is_valid:
        token_msg = message.replace('✅ ', '') if message else 'Valid'
        token_status = f"✅ Token: {token_msg}"
    else:
        token_status = "❌ Token Invalid"

    col1, col2, col3 = st.columns([2, 2, 1])

    # Проверить закреплен ли expander
    expander_id = f"client_{client_id}"
    is_pinned = _is_expander_pinned(expander_id, default=False)

    with col1:
        with st.expander(f"{status_icon} {client_name}", expanded=is_pinned):
            # Кнопка Pin/Unpin
            _render_pin_checkbox(expander_id)
            
            scale = client_config.settings.get('scale_method', 'N/A') if client_config else 'N/A'
            st.markdown(
                f"**Active:** {'Yes' if is_enabled else 'No'} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; **Scale:** {scale}"
            )
            if is_valid:
                render_client_info(client_id)

    with col2:
        st.markdown(f"<div style='padding-top: 8px;'>{token_status}</div>", unsafe_allow_html=True)

    with col3:
        from app.core.paths import TOKEN_PATH
        token_file = str(TOKEN_PATH / f"{client_id}_tokens.json")

        if should_show_auth_button(is_valid, token_file) and credentials_ok:
            st.markdown("<div style='padding-top: 3px;'></div>", unsafe_allow_html=True)

            if 'auth_errors' not in st.session_state:
                st.session_state.auth_errors = {}

            has_error = st.session_state.auth_errors.get(client_id, False)

            btn_icon = "⚠️" if has_error else "🔐"
            btn_help = "Authorization failed. Retry?" if has_error else (
                "Authorization required" if not is_valid else "Weekly token refresh"
            )

            if st.button(f"{btn_icon} Auth", key=f"auth_{client_id}", type="primary", help=btn_help):
                with st.spinner("Authorizing..."):
                    success = authorize_client(client_id)
                    st.session_state.auth_errors[client_id] = not success
                    st.rerun()


def render_client_info(client_id: str):
    """Краткая информация о клиенте (из кэша)"""

    from app.core.cache_manager import get_cached_client

    cached = get_cached_client(client_id)

    if not cached:
        st.caption("⚠️ No data. Click Refresh.")
        return

    total_value = cached.get('balances', {}).get('liquidation_value', 0)
    positions_count = cached.get('positions_count', 0)
    total_pl = cached.get('total_pl', 0)

    st.markdown(f"**Total:** ${total_value:,.0f} | **Positions:** {positions_count} | **P&L:** ${total_pl:+,.0f}")


# ═══════════════════════════════════════════════════════════════
# 3️⃣ MARKET STATUS
# ═══════════════════════════════════════════════════════════════

def render_market_status():
    """Статус рынка"""

    from app.core.market_calendar import get_market_status, get_next_holiday

    status = get_market_status()
    next_holiday = get_next_holiday()

    col1, col2, col3 = st.columns(3)

    with col1:
        status_icons = {
            'OPEN': '🟢',
            'PRE_MARKET': '🟡',
            'AFTER_HOURS': '🟡',
            'CLOSED': '🔴',
            'HOLIDAY': '🔴',
            'WEEKEND': '🔴'
        }
        icon = status_icons.get(status['status'], '⚪')
        st.markdown(f"{icon} **{status['message']}**")

    with col2:
        st.markdown(f"**{status['next_event']}**")

    with col3:
        if next_holiday:
            st.markdown(f"**Next Holiday:** {next_holiday['name']} ({next_holiday['date'][5:]})")
        else:
            st.markdown("**Next Holiday:** --")


# ═══════════════════════════════════════════════════════════════
# 4️⃣ SCHWAB API STATUS
# ═══════════════════════════════════════════════════════════════

def render_api_status(main_status: Dict):
    """Статус Schwab API"""

    col1, col2, col3 = st.columns(3)

    with col1:
        if main_status['is_valid']:
            st.markdown("🟢 **Schwab API:** Operational")
        else:
            st.markdown("🔴 **API:** Not Connected")

    with col2:
        st.markdown("**Version:** v1")

    with col3:
        st.markdown("**Rate Limit:** Standard")


# ═══════════════════════════════════════════════════════════════
# 5️⃣ SYNC HISTORY
# ═══════════════════════════════════════════════════════════════

def render_sync_history():
    """История синхронизаций всех клиентов"""

    expander_id = "sync_history"
    is_pinned = _is_expander_pinned(expander_id, default=False)

    with st.expander("**📜 Recent Sync History**", expanded=is_pinned):
        # Кнопка Pin/Unpin
        _render_pin_checkbox(expander_id)

        # Собрать историю всех клиентов
        all_history = []
        clients_dir = Path("data/clients")

        if clients_dir.exists():
            for history_file in clients_dir.glob("*_history.json"):
                try:
                    history = load_json(str(history_file), default=[])
                    all_history.extend(history)
                except (KeyError, TypeError, ValueError):
                    pass

        if not all_history:
            st.info("No sync history yet")
            return

        # Сортировать по времени (новые первые)
        all_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Показать последние 10 записей
        for entry in all_history[:10]:
            timestamp = entry.get('timestamp', '')[:16].replace('T', ' ')
            client_name = entry.get('client_name', 'Unknown')
            dry_run = entry.get('dry_run', False)
            summary = entry.get('summary', {})

            total_deltas = summary.get('total_deltas', len(entry.get('deltas', [])))
            orders_success = summary.get('orders_success', len(entry.get('results', [])))

            if dry_run:
                mode_icon = "🧪"
            else:
                mode_icon = "🔴"

            if total_deltas == 0:
                status_icon = "➖"
            elif orders_success > 0:
                status_icon = "✅"
            else:
                status_icon = "❌"

            st.markdown(
                f"{status_icon} **{timestamp}** | {mode_icon} | "
                f"**{client_name}** | {orders_success} orders | {total_deltas} deltas"
            )


# ═══════════════════════════════════════════════════════════════
# 6️⃣ POSITION COMPARISON
# ═══════════════════════════════════════════════════════════════

def render_position_comparison(main_status: Dict, client_manager):
    """Сравнение позиций Main vs Clients (из кэша)"""

    from app.core.cache_manager import get_cached_main_account

    expander_id = "position_comparison"
    is_pinned = _is_expander_pinned(expander_id, default=False)

    if not main_status['is_valid']:
        with st.expander("**🔄 Position Sync Status**", expanded=is_pinned):
            _render_pin_checkbox(expander_id)
            st.info("Authorize Main Account to see position comparison")
        return

    enabled_clients = client_manager.get_enabled_clients()

    if not enabled_clients:
        with st.expander("**🔄 Position Sync Status**", expanded=is_pinned):
            _render_pin_checkbox(expander_id)
            st.info("No active clients to compare")
        return

    cached = get_cached_main_account()

    if not cached:
        with st.expander("**🔄 Position Sync Status**", expanded=is_pinned):
            _render_pin_checkbox(expander_id)
            st.info("No cached data. Click Refresh.")
        return

    positions = cached.get('positions', [])

    if not positions:
        with st.expander("**🔄 Position Sync Status**", expanded=is_pinned):
            _render_pin_checkbox(expander_id)
            st.info("No positions in Main Account")
        return

    with st.expander("**🔄 Position Sync Status**", expanded=is_pinned):
        # Кнопка Pin/Unpin
        _render_pin_checkbox(expander_id)
        
        sorted_positions = sorted(positions, key=lambda x: x.get('market_value', 0), reverse=True)[:5]

        for pos in sorted_positions:
            symbol = pos.get('symbol', 'N/A')
            quantity = int(pos.get('quantity', 0))
            st.markdown(f"**{symbol}:** {quantity} shares | ✅ Tracking")
