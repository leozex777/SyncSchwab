
# cache_manager.py
# app.core.cache_manager.py

import streamlit as st
from datetime import datetime
from typing import Dict, Optional
import os

from app.core.config import get_main_client, get_hash_account, build_client_for_slave
from app.core.json_utils import load_json, save_json
from app.core.paths import DATA_DIR
from app.core.logger import logger
from app.models.copier.entities import parse_positions_from_account_details
from dotenv import load_dotenv

load_dotenv()

CACHE_FILE = DATA_DIR / "account_cache.json"


# ═══════════════════════════════════════════════════════════════
# ФЛАГ ОБНОВЛЕНИЯ КЭША (для автообновления GUI)
# ═══════════════════════════════════════════════════════════════

# Файл-флаг для межпроцессной коммуникации
CACHE_UPDATED_FLAG = DATA_DIR / ".cache_updated"


def set_cache_updated(updated: bool = True):
    """
    Установить флаг, что кэш обновился.
    Использует файл-флаг для работы из фоновых потоков.
    """
    try:
        if updated:
            # Создать файл-флаг
            CACHE_UPDATED_FLAG.touch()
            logger.debug("Cache updated flag set (file)")
        else:
            # Удалить файл-флаг
            if CACHE_UPDATED_FLAG.exists():
                CACHE_UPDATED_FLAG.unlink()
    except (OSError, IOError, PermissionError) as e:
        logger.debug(f"Could not set cache flag: {e}")


def check_cache_updated() -> bool:
    """
    Проверить и сбросить флаг обновления кэша.
    Читает из файла (работает из любого потока).
    """
    try:
        if CACHE_UPDATED_FLAG.exists():
            CACHE_UPDATED_FLAG.unlink()  # Сбросить флаг
            logger.debug("Cache updated flag consumed (file)")
            return True
        return False
    except (OSError, IOError, PermissionError):
        return False


def get_cache_updated() -> bool:
    """Алиас для check_cache_updated (для совместимости)"""
    return check_cache_updated()


# ═══════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ ВРЕМЕНИ ДЛЯ SIDEBAR
# ═══════════════════════════════════════════════════════════════

def format_cache_age() -> tuple[str, str]:
    """
    Форматировать возраст кэша для отображения в sidebar.
    
    Returns:
        tuple: (formatted_time, color_emoji)
        
    Формат:
        ≤15 мин: 🟢 M:SS (например "3:15")
        16-60 мин: 🟡 X min (например "16 min")  
        >60 мин: 🔴 Xh : Y min (например "1h : 15 min")
    """
    # Читаем из файла напрямую (не из session_state)
    cached_data = load_json(str(CACHE_FILE), default={})
    timestamp_str = cached_data.get('last_updated')
    
    if not timestamp_str:
        return "no data", "🔴"
    
    try:
        last_update = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        diff = now - last_update
        
        total_seconds = int(diff.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        hours = minutes // 60
        
        if minutes <= 15:
            # ≤15 мин: зеленый, формат M:SS
            return f"{minutes}:{seconds:02d}", "🟢"
        elif minutes <= 60:
            # 16-60 мин: желтый, формат X min
            return f"{minutes} min", "🟡"
        else:
            # >60 мин: красный, формат Xh : Y min
            remaining_min = minutes % 60
            return f"{hours}h : {remaining_min} min", "🔴"
            
    except (ValueError, TypeError):
        return "error", "🔴"


def init_cache():
    """Инициализация кэша в session_state"""

    if 'account_cache' not in st.session_state:
        logger.debug("Initializing cache from file...")
        cached_data = load_json(str(CACHE_FILE), default={})

        st.session_state.account_cache = {
            'main_account': cached_data.get('main_account'),
            'clients': cached_data.get('clients', {}),
            'last_updated': cached_data.get('last_updated')
        }
        logger.debug("Cache initialized")


def get_cache() -> Dict:
    """Получить кэш"""
    init_cache()
    return st.session_state.account_cache


def is_cache_empty() -> bool:
    """Проверить, пустой ли кэш"""
    cache = get_cache()
    return cache.get('main_account') is None


def get_cached_main_account() -> Optional[Dict]:
    """Получить данные Main Account из кэша"""
    cache = get_cache()
    return cache.get('main_account')


def get_cached_client(client_id: str) -> Optional[Dict]:
    """Получить данные клиента из кэша"""
    cache = get_cache()
    return cache.get('clients', {}).get(client_id)


def get_cache_timestamp() -> Optional[str]:
    """Получить время последнего обновления кэша"""
    cache = get_cache()
    return cache.get('last_updated')


def update_main_account_cache() -> Optional[Dict]:
    """Обновить кэш Main Account из API"""

    logger.info("Updating main account cache from API...")

    try:
        client = get_main_client()
        if not client:
            logger.warning("Main client not available")
            return None

        account_number = os.getenv('MAIN_ACCOUNT_NUMBER')
        if not account_number:
            logger.warning("MAIN_ACCOUNT_NUMBER not set in .env")
            return None

        # Оптимизация: сначала читаем hash из client_manager (без API)
        account_hash = None
        if 'client_manager' in st.session_state:
            account_hash = st.session_state.client_manager.main_account.get('account_hash')
            if account_hash:
                logger.info(f"Using cached account_hash: {account_hash[:8]}...")  # ← INFO вместо DEBUG

        # API вызов только если hash пустой
        if not account_hash:
            logger.info("Fetching account_hash from API (first time or refresh)...")
            account_hash = get_hash_account(client, account_number)
            if not account_hash:
                logger.warning(f"Could not get account hash for {account_number}")
                return None

            # Сохранить для будущих вызовов
            if 'client_manager' in st.session_state:
                st.session_state.client_manager.set_main_account(account_hash, account_number)
                logger.info(f"Main account hash saved: {account_hash[:8]}...")

        # Получить данные из API
        logger.debug("Fetching account details from Schwab API...")
        details = client.account_details(account_hash, fields='positions').json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = parse_positions_from_account_details(details)

        # Сформировать данные для кэша
        cache_data = {
            'account_number': account_number,
            'account_hash': account_hash,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0,
            'updated_at': datetime.now().isoformat()
        }

        # Сохранить в session_state
        init_cache()
        st.session_state.account_cache['main_account'] = cache_data
        st.session_state.account_cache['last_updated'] = datetime.now().isoformat()

        # Сохранить в файл
        _save_cache_to_file()

        logger.info(
            f"Main account cache updated: {len(positions)} positions, "
            f"${balances.get('liquidationValue', 0):,.0f} total")
        return cache_data

    except (KeyError, TypeError, ValueError, AttributeError) as e:
        logger.error(f"Error updating main account cache: {e}")
        return None


def update_client_cache(client_id: str) -> Optional[Dict]:
    """Обновить кэш клиента из API"""

    logger.info(f"Updating client cache: {client_id}")

    try:
        from app.gui.utils.env_manager import load_client_from_env

        env_data = load_client_from_env(client_id)

        if not all([env_data.get('key_id'), env_data.get('client_secret')]):
            logger.warning(f"Client {client_id}: credentials not found in .env")
            return None

        slave_client = build_client_for_slave(
            client_id,
            env_data['key_id'],
            env_data['client_secret'],
            env_data.get('redirect_uri', 'https://127.0.0.1:8182')
        )

        # Получить account_hash из client_manager
        client_manager = st.session_state.client_manager
        client_config = client_manager.get_client(client_id)

        if not client_config or not client_config.account_hash:
            logger.warning(f"Client {client_id}: account_hash not found")
            return None

        # Получить данные из API
        logger.debug(f"Fetching {client_id} account details from Schwab API...")
        details = slave_client.account_details(client_config.account_hash, fields='positions').json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = parse_positions_from_account_details(details)

        # Сформировать данные для кэша
        cache_data = {
            'client_id': client_id,
            'client_name': client_config.name,
            'account_hash': client_config.account_hash,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0,
            'updated_at': datetime.now().isoformat()
        }

        # Сохранить в session_state
        init_cache()
        if 'clients' not in st.session_state.account_cache:
            st.session_state.account_cache['clients'] = {}
        st.session_state.account_cache['clients'][client_id] = cache_data
        st.session_state.account_cache['last_updated'] = datetime.now().isoformat()

        # Сохранить в файл
        _save_cache_to_file()

        logger.info(f"Client {client_id} cache updated: {len(positions)} positions")
        return cache_data

    except (KeyError, TypeError, ValueError, AttributeError) as e:
        logger.error(f"Error updating client {client_id} cache: {e}")
        return None


def update_all_cache() -> bool:
    """Обновить весь кэш (Main + все клиенты)"""

    logger.info("Updating all cache...")
    success = True

    # Обновить Main Account
    if update_main_account_cache() is None:
        success = False

    # Обновить всех клиентов
    client_manager = st.session_state.client_manager
    enabled_count = 0

    for client_config in client_manager.clients:
        if client_config.enabled:
            enabled_count += 1
            if update_client_cache(client_config.id) is None:
                success = False

    logger.info(f"Cache update complete: {enabled_count} clients, success={success}")
    
    # Установить флаг для автообновления GUI
    set_cache_updated(True)
    
    return success


def clear_cache():
    """Очистить кэш"""

    logger.info("Clearing cache...")

    st.session_state.account_cache = {
        'main_account': None,
        'clients': {},
        'last_updated': None
    }

    # Удалить файл кэша
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        logger.debug("Cache file deleted")


def _save_cache_to_file():
    """Сохранить кэш в файл"""

    cache = get_cache()
    save_json(str(CACHE_FILE), cache)
    logger.debug("Cache saved to file")


def ensure_cache_loaded():
    """
    Проверить и загрузить кэш при первом запуске программы.
    Вызывается только при старте (если кэш пустой).
    
    Обновление происходит если токены OK.
    Если не удалось - пишем в лог и продолжаем.
    """
    if is_cache_empty():
        logger.info("Cache is empty, attempting to load from API...")
        try:
            success = update_all_cache()
            if not success:
                logger.warning("Failed to update cache at startup (tokens may be invalid)")
        except Exception as e:
            logger.warning(f"Could not update cache at startup: {e}")


# ═══════════════════════════════════════════════════════════════
# ФОНОВОЕ ОБНОВЛЕНИЕ КЭША (для старта GUI)
# ═══════════════════════════════════════════════════════════════

def update_all_cache_background():
    """
    Обновить кэш в фоновом потоке.
    
    Вызывается из main.py при старте GUI.
    Не использует st.session_state (работает в отдельном потоке).
    
    - Если успех → set_cache_updated(True) → GUI обновится
    - Если ошибка → записать в лог
    """
    # Явно загрузить .env (фоновый поток не видит переменные из main)
    load_dotenv()
    
    logger.info("Background: Cache update started...")
    
    try:
        # Загрузить текущий кэш из файла
        cache = load_json(str(CACHE_FILE), default={
            'main_account': None,
            'clients': {},
            'last_updated': None
        })
        
        success = True
        
        # ═══════════════════════════════════════════════════════════════
        # ОБНОВИТЬ MAIN ACCOUNT
        # ═══════════════════════════════════════════════════════════════
        main_data = _update_main_account_background()
        if main_data:
            cache['main_account'] = main_data
        else:
            success = False
        
        # ═══════════════════════════════════════════════════════════════
        # ОБНОВИТЬ КЛИЕНТОВ
        # ═══════════════════════════════════════════════════════════════
        clients_data = _update_clients_background()
        if clients_data is not None:
            cache['clients'] = clients_data
        else:
            success = False
        
        # Обновить timestamp
        cache['last_updated'] = datetime.now().isoformat()
        
        # Сохранить в файл
        save_json(str(CACHE_FILE), cache)
        
        # Установить флаг для обновления GUI
        set_cache_updated(True)
        
        if success:
            logger.info("Background: Cache update completed successfully")
        else:
            logger.warning("Background: Cache update completed with errors")
            
    except Exception as e:
        logger.error(f"Background: Cache update failed: {e}")


def _update_main_account_background() -> Optional[Dict]:
    """
    Обновить Main Account в фоновом потоке.
    Не использует st.session_state.
    """
    try:
        from app.core.config import build_main_client
        
        # Получить credentials из .env
        app_key = os.getenv('MAIN_KEY_ID')
        app_secret = os.getenv('MAIN_CLIENT_SECRET')
        account_number = os.getenv('MAIN_ACCOUNT_NUMBER')
        
        if not all([app_key, app_secret, account_number]):
            logger.warning("Background: Main account credentials not found in .env")
            return None
        
        # Создать клиента
        client = build_main_client()
        if not client:
            logger.warning("Background: Could not create main client")
            return None
        
        # Получить account_hash
        account_hash = get_hash_account(client, account_number)
        if not account_hash:
            logger.warning(f"Background: Could not get account hash for {account_number}")
            return None
        
        # Получить данные из API
        logger.debug("Background: Fetching main account details from Schwab API...")
        details = client.account_details(account_hash, fields='positions').json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = parse_positions_from_account_details(details)
        
        # Сформировать данные
        cache_data = {
            'account_number': account_number,
            'account_hash': account_hash,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0,
            'updated_at': datetime.now().isoformat()
        }
        
        logger.info(
            f"Background: Main account updated: {len(positions)} positions, "
            f"${balances.get('liquidationValue', 0):,.0f} total"
        )
        return cache_data
        
    except Exception as e:
        logger.error(f"Background: Error updating main account: {e}")
        return None


def _update_clients_background() -> Optional[Dict]:
    """
    Обновить всех клиентов в фоновом потоке.
    Не использует st.session_state.
    """
    try:
        from app.core.paths import CONFIG_DIR
        
        # Загрузить список клиентов из файла
        clients_file = CONFIG_DIR / "clients.json"
        data = load_json(str(clients_file), default={})
        
        # Формат: {"main_account": {...}, "slave_accounts": [...]}
        clients_list = data.get('slave_accounts', [])
        
        if not clients_list:
            logger.debug("Background: No clients configured")
            return {}
        
        clients_cache = {}
        
        for client_data in clients_list:
            # Проверить что это словарь
            if not isinstance(client_data, dict):
                continue
                
            client_id = client_data.get('id')
            if not client_id:
                continue
            
            # Пропустить disabled клиентов
            if not client_data.get('enabled', False):
                continue
            
            client_cache = _update_single_client_background(client_id, client_data)
            if client_cache:
                clients_cache[client_id] = client_cache
        
        logger.info(f"Background: {len(clients_cache)} clients updated")
        return clients_cache
        
    except Exception as e:
        logger.error(f"Background: Error updating clients: {e}")
        return None


def _update_single_client_background(client_id: str, client_data: Dict) -> Optional[Dict]:
    """
    Обновить одного клиента в фоновом потоке.
    """
    try:
        from app.gui.utils.env_manager import load_client_from_env
        
        env_data = load_client_from_env(client_id)
        
        if not all([env_data.get('key_id'), env_data.get('client_secret')]):
            logger.warning(f"Background: Client {client_id} credentials not found")
            return None
        
        # Создать клиента
        slave_client = build_client_for_slave(
            client_id,
            env_data['key_id'],
            env_data['client_secret'],
            env_data.get('redirect_uri', 'https://127.0.0.1:8182')
        )
        
        account_hash = client_data.get('account_hash')
        if not account_hash:
            logger.warning(f"Background: Client {client_id} account_hash not found")
            return None
        
        # Получить данные из API
        details = slave_client.account_details(account_hash, fields='positions').json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = parse_positions_from_account_details(details)
        
        cache_data = {
            'client_id': client_id,
            'client_name': client_data.get('name', client_id),
            'account_hash': account_hash,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0,
            'updated_at': datetime.now().isoformat()
        }
        
        logger.info(f"Background: Client {client_id} updated: {len(positions)} positions")
        return cache_data
        
    except Exception as e:
        logger.error(f"Background: Error updating client {client_id}: {e}")
        return None