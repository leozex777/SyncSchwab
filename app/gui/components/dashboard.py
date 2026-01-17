
# dashboard.py
# app.gui.components.dashboard

import streamlit as st
import pandas as pd
from typing import Dict

from app.core.token_checker import check_all_tokens
from app.utils.schwab_auth import authorize_main_account, authorize_client
from app.core.json_utils import load_json
from app.core.config_cache import ConfigCache
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path

from app.core.market_calendar import update_market_calendar
update_market_calendar()

load_dotenv()


# ═══════════════════════════════════════════════════════════════
# EXPANDER STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def _get_ui_state_file() -> Path:
    """Путь к файлу состояния UI"""
    return Path("config/ui_state.json")


# Валидные ключи expander (только актуальные)
_VALID_EXPANDER_IDS = {"sync_history"}


def _load_expander_states() -> dict:
    """Загрузить состояния всех expanders (через кэш)"""
    return ConfigCache.get_ui_state()


def _save_expander_state(expander_id: str, is_pinned: bool):
    """Сохранить состояние expander и обновить кэш"""
    # Создать чистый state только с валидными ключами
    state = {"dashboard_expanders": {}}
    
    # Загрузить текущее состояние и оставить только валидные
    old_state = _load_expander_states()
    old_expanders = old_state.get("dashboard_expanders", {})
    
    for key in _VALID_EXPANDER_IDS:
        if key in old_expanders:
            state["dashboard_expanders"][key] = old_expanders[key]
    
    # Добавить/обновить текущий expander
    if expander_id in _VALID_EXPANDER_IDS:
        state["dashboard_expanders"][expander_id] = is_pinned
    
    ConfigCache.save_ui_state(state)


def _is_expander_pinned(expander_id: str, default: bool = False) -> bool:
    """Проверить закреплен ли expander"""
    state = _load_expander_states()
    return state.get("dashboard_expanders", {}).get(expander_id, default)


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


def get_token_status_info(is_valid: bool, message: str, token_file_path: str = None) -> dict:
    """
    Получить информацию о статусе токена для отображения в таблице.
    
    Returns:
        dict: {
            'display': str - текст для отображения,
            'needs_auth': bool - нужна ли авторизация,
            'variant': str - 'valid', 'invalid', 'sunday'
        }
    """
    if is_valid:
        # Токен валиден
        if is_sunday():
            if token_file_path and was_authorized_today(token_file_path):
                # Воскресенье, но уже авторизовались сегодня
                time_left = message.replace('✅ ', '').replace('Valid ', '').strip('()')
                return {
                    'display': f"✅ Valid ({time_left})",
                    'needs_auth': False,
                    'variant': 'valid'
                }
            else:
                # Воскресенье, нужен refresh
                return {
                    'display': "⚠️ Sunday refresh",
                    'needs_auth': True,
                    'variant': 'sunday'
                }
        else:
            # Обычный день, токен валиден
            time_left = message.replace('✅ ', '').replace('Valid ', '').strip('()')
            return {
                'display': f"✅ Valid ({time_left})",
                'needs_auth': False,
                'variant': 'valid'
            }
    else:
        # Токен невалиден
        return {
            'display': "❌ Invalid",
            'needs_auth': True,
            'variant': 'invalid'
        }


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
    # 1️⃣ ACCOUNTS INFORMATION TABLE
    # ═══════════════════════════════════════════════════
    render_accounts_table(status, client_manager)

    # ═══════════════════════════════════════════════════
    # 2️⃣ POSITION SYNC STATUS TABLE
    # ═══════════════════════════════════════════════════
    render_positions_table(status['main'], client_manager)

    # ═══════════════════════════════════════════════════
    # 3️⃣ SYNC HISTORY
    # ═══════════════════════════════════════════════════
    render_sync_history()

    # ═══════════════════════════════════════════════════
    # 4️⃣ MARKET STATUS
    # ═══════════════════════════════════════════════════
    render_market_status()

    # ═══════════════════════════════════════════════════
    # 5️⃣ SCHWAB API STATUS
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
# 1️⃣ ACCOUNTS INFORMATION TABLE
# ═══════════════════════════════════════════════════════════════

def render_accounts_table(status: Dict, client_manager):
    """Таблица Accounts Information с кнопками Auth слева"""
    
    from app.core.cache_manager import get_cached_main_account, get_cached_client
    from app.core.paths import TOKEN_PATH
    
    st.markdown("#### 📊 Accounts Information")
    
    rows = []
    auth_actions = []  # Список: None если не нужна авторизация, или dict с данными
    
    # ═══════════════════════════════════════════════════
    # MAIN ACCOUNT
    # ═══════════════════════════════════════════════════
    main_status = status['main']
    
    if main_status['credentials_ok']:
        cached = get_cached_main_account()
        
        # Token status
        token_file = str(TOKEN_PATH / "main_tokens.json")
        token_info = get_token_status_info(
            main_status['is_valid'],
            main_status.get('message', ''),
            token_file
        )
        
        if cached:
            balances = cached.get('balances', {})
            positions = cached.get('positions', [])
            total_value = balances.get('liquidation_value', 0)
            positions_value = sum(p.get('market_value', 0) for p in positions)
            cash_balance = balances.get('cash_balance', 0)
            buying_power = balances.get('buying_power', 0)
            total_pl = cached.get('total_pl', 0)
            
            rows.append({
                'Account': '🏦 Main',
                'Total Value': f"${total_value:,.0f}",
                'Positions Value': f"${positions_value:,.2f}",
                'cashBalance': f"${cash_balance:,.0f}",
                'buyingPower': f"${buying_power:,.0f}",
                'Open Positions': len(positions),
                'P&L': f"${total_pl:+,.2f}",
                'Token status': token_info['display']
            })
        else:
            rows.append({
                'Account': '🏦 Main',
                'Total Value': 'N/A',
                'Positions Value': 'N/A',
                'cashBalance': 'N/A',
                'buyingPower': 'N/A',
                'Open Positions': 0,
                'P&L': 'N/A',
                'Token status': token_info['display']
            })
        
        if token_info['needs_auth']:
            auth_actions.append({'type': 'main', 'id': None, 'name': 'Main'})
        else:
            auth_actions.append(None)
    
    # ═══════════════════════════════════════════════════
    # CLIENT ACCOUNTS (только Active)
    # ═══════════════════════════════════════════════════
    clients_status = status.get('clients', [])
    
    for client_status in clients_status:
        # Только enabled клиенты
        if not client_status.get('is_enabled', False):
            continue
            
        client_id = client_status['client_id']
        client_name = client_status['client_name']
        is_valid = client_status['is_valid']
        credentials_ok = client_status['credentials_ok']
        message = client_status.get('message', '')
        
        if credentials_ok:
            cached = get_cached_client(client_id)
            
            # Token status
            token_file = str(TOKEN_PATH / f"{client_id}_tokens.json")
            token_info = get_token_status_info(is_valid, message, token_file)
            
            if cached:
                balances = cached.get('balances', {})
                positions_count = cached.get('positions_count', 0)
                total_value = balances.get('liquidation_value', 0)
                positions_value = balances.get('positions_value', 0)
                cash_balance = balances.get('cash_balance', 0)
                buying_power = balances.get('buying_power', 0)
                total_pl = cached.get('total_pl', 0)
                
                rows.append({
                    'Account': f'👤 {client_name}',
                    'Total Value': f"${total_value:,.0f}",
                    'Positions Value': f"${positions_value:,.2f}",
                    'cashBalance': f"${cash_balance:,.0f}",
                    'buyingPower': f"${buying_power:,.0f}",
                    'Open Positions': positions_count,
                    'P&L': f"${total_pl:+,.2f}",
                    'Token status': token_info['display']
                })
            else:
                rows.append({
                    'Account': f'👤 {client_name}',
                    'Total Value': 'N/A',
                    'Positions Value': 'N/A',
                    'cashBalance': 'N/A',
                    'buyingPower': 'N/A',
                    'Open Positions': 0,
                    'P&L': 'N/A',
                    'Token status': token_info['display']
                })
            
            if token_info['needs_auth']:
                auth_actions.append({'type': 'client', 'id': client_id, 'name': client_name})
            else:
                auth_actions.append(None)
    
    # ═══════════════════════════════════════════════════
    # DISPLAY TABLE
    # ═══════════════════════════════════════════════════
    if not rows:
        st.info("No accounts configured. Go to **Main Account Management** to add accounts.")
        return
    
    df = pd.DataFrame(rows)
    
    # Проверить есть ли хоть одна кнопка auth
    has_any_auth = any(action is not None for action in auth_actions)
    
    if has_any_auth:
        # CSS для компактных кнопок и минимальных отступов
        st.markdown("""
        <style>
        button[data-testid="stBaseButton-primary"] {
            padding: 0.15rem 0.4rem !important;
            font-size: 0.75rem !important;
            min-height: 31px !important;
            max-height: 31px !important;
            line-height: 1 !important;
        }
        button[data-testid="stBaseButton-primary"] p {
            font-size: 0.75rem !important;
            margin: 0 !important;
        }
        /* Уменьшить отступы между кнопками */
        .stVerticalBlock > div.stElementContainer:has(.stButton) {
            margin-bottom: -12px !important;
            padding: 0 !important;
        }
        .stVerticalBlock {
            gap: 1 !important;
        }
        /* Опустить все кнопки вниз на ~1мм (4px) */
        div[data-testid="column"]:first-child .stVerticalBlock {
            margin-top: 4px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Кнопки слева, таблица справа
        col_btns, col_table = st.columns([0.7, 9.3])
        
        with col_btns:
            # Пустое место для заголовка таблицы
            st.markdown("<div style='height: 39px;'></div>", unsafe_allow_html=True)
            
            # Кнопки для каждой строки
            for i, action in enumerate(auth_actions):
                if action is not None:
                    if st.button("🔐 Auth", key=f"auth_row_{i}", type="primary"):
                        with st.spinner("Authorizing..."):
                            if action['type'] == 'main':
                                authorize_main_account()
                            else:
                                authorize_client(action['id'])
                            st.rerun()
                else:
                    # Пустое место для выравнивания
                    st.markdown("<div style='height: 35px;'></div>", unsafe_allow_html=True)
        
        with col_table:
            st.dataframe(
                df,
                width='stretch',
                hide_index=True,
                height=min(len(rows) * 35 + 38, 300)
            )
    else:
        # Все авторизованы - таблица на 100%
        st.dataframe(
            df,
            width='stretch',
            hide_index=True,
            height=min(len(rows) * 35 + 38, 300)
        )
    
    # Используем client_manager для будущих расширений
    _ = client_manager


# ═══════════════════════════════════════════════════════════════
# 2️⃣ POSITION SYNC STATUS TABLE
# ═══════════════════════════════════════════════════════════════

def render_positions_table(main_status: Dict, client_manager):
    """Таблица позиций Main vs Clients"""
    
    from app.core.cache_manager import get_cached_main_account, get_cached_client
    
    st.markdown("#### 🔄 Position Sync Status: Accounts")
    
    # Показывать только если Main авторизован
    if not main_status['is_valid']:
        st.info("Authorize Main Account to see position comparison")
        return
    
    cached_main = get_cached_main_account()
    
    if not cached_main:
        st.info("No cached data. Click Refresh to load data.")
        return
    
    main_positions = cached_main.get('positions', [])
    
    if not main_positions:
        st.info("No positions in Main Account")
        return
    
    # Собрать все символы
    symbols = set()
    for pos in main_positions:
        symbols.add(pos.get('symbol', 'N/A'))
    
    # Получить ТОЛЬКО enabled клиентов
    enabled_clients = client_manager.get_enabled_clients()
    
    if not enabled_clients:
        # Показать только Main если нет активных клиентов
        rows = []
        for symbol in sorted(symbols):
            main_qty = 0
            for pos in main_positions:
                if pos.get('symbol') == symbol:
                    main_qty = int(pos.get('quantity', 0))
                    break
            rows.append({'ETF/Equity': symbol, 'Main': main_qty})
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, width='stretch', hide_index=True)
        return
    
    # Собрать позиции клиентов
    client_positions = {}
    for client in enabled_clients:
        cached = get_cached_client(client.id)
        if cached:
            positions = cached.get('positions', [])
            client_positions[client.name] = {
                p.get('symbol'): int(p.get('quantity', 0)) for p in positions
            }
            # Добавить символы клиента
            for pos in positions:
                symbols.add(pos.get('symbol', 'N/A'))
        else:
            client_positions[client.name] = {}
    
    # Создать DataFrame
    rows = []
    for symbol in sorted(symbols):
        row = {'ETF/Equity': symbol}
        
        # Main quantity
        main_qty = 0
        for pos in main_positions:
            if pos.get('symbol') == symbol:
                main_qty = int(pos.get('quantity', 0))
                break
        row['Main'] = main_qty
        
        # Client quantities (только enabled)
        for client in enabled_clients:
            client_qty = client_positions.get(client.name, {}).get(symbol, 0)
            row[client.name] = client_qty
        
        rows.append(row)
    
    if rows:
        df = pd.DataFrame(rows)
        
        st.dataframe(
            df,
            width='stretch',
            hide_index=True,
            height=min(len(rows) * 35 + 38, 300)
        )
    else:
        st.info("No positions to display")


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
    
    # Разделитель перед секцией
#    st.divider()
    
    expander_id = "sync_history"
    is_pinned = _is_expander_pinned(expander_id, default=False)
    
    # CSS для прозрачной кнопки pin (как в client_management.py)
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
    
    # Заголовок с прозрачной кнопкой pin СЛЕВА
    col_pin, col_title = st.columns([0.08, 3])
    
    with col_pin:
        icon = "📍" if is_pinned else "📌"
        if st.button(
            icon,
            key=f"pin_btn_{expander_id}",
            help="Pin/Unpin this section",
            type="tertiary"
        ):
            _save_expander_state(expander_id, not is_pinned)
            st.rerun()
    
    with col_title:
        # Название секции зависит от режима
        general_settings = ConfigCache.get_general_settings()
        operating_mode = general_settings.get('operating_mode', 'monitor')
        
        if operating_mode == 'live':
            st.markdown("#### 📜 Recent Order History")
        elif operating_mode == 'monitor':
            st.markdown("#### 📜 Recent Delta History")
        else:
            st.markdown("#### 📜 Recent Sync History")

    with st.expander("📜", expanded=is_pinned):
        # Собрать историю всех клиентов
        all_history = []
        clients_dir = Path("data/clients")

        if clients_dir.exists():
            # Выбрать паттерн файла в зависимости от режима
            if operating_mode == 'live':
                # LIVE: только *_history.json (без _dry)
                history_files = [f for f in clients_dir.glob("*_history.json") if "_dry" not in f.name]
            else:
                # Simulation / Dry Run: только *_history_dry.json
                history_files = clients_dir.glob("*_history_dry.json")
            
            for history_file in history_files:
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

        # Контейнер с прокруткой (показывать ~4 записи, всего 10)
        with st.container(height=140):
            for entry in all_history[:10]:
                timestamp = entry.get('timestamp', '')[:16].replace('T', ' ')
                client_name = entry.get('client_name', 'Unknown')
                
                # Определить режим
                entry_operating_mode = entry.get('operating_mode', '')
                dry_run = entry.get('monitor', False)
                
                if entry_operating_mode == 'simulation':
                    mode_icon = "🔶"
                elif entry_operating_mode == 'live' or not dry_run:
                    mode_icon = "🔴"
                else:
                    mode_icon = "🧪"
                
                summary = entry.get('summary', {})
                total_deltas = summary.get('total_deltas', len(entry.get('deltas', [])))
                orders_success = summary.get('orders_success', len(entry.get('results', [])))

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
