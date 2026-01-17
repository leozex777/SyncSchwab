
# cache_manager.py
# app.core.cache_manager.py

from datetime import datetime
from typing import Dict, Optional
import os
import threading

from app.core.config import get_main_client, get_hash_account, build_client_for_slave
from app.core.json_utils import load_json, save_json
from app.core.paths import DATA_DIR
from app.core.logger import logger
from app.models.copier.entities import parse_positions_from_account_details
from dotenv import load_dotenv


def _has_streamlit_context() -> bool:
    """Проверить есть ли Streamlit контекст"""
    # Worker mode - сразу возвращаем False без проверки streamlit
    if os.environ.get('SYNC_WORKER_MODE'):
        return False
    
    try:
        import importlib
        scriptrunner = importlib.import_module('streamlit.runtime.scriptrunner')
        ctx_func = getattr(scriptrunner, 'get_script_run_ctx', None)
        return ctx_func() is not None if ctx_func else False
    except (ImportError, AttributeError):
        return False


class _LazyStreamlit:
    """
    Ленивый импорт streamlit — загружается только при первом обращении
    и только если есть Streamlit контекст (не в Worker).
    """
    _st = None
    _checked = False
    _has_context = False
    
    @property
    def session_state(self):
        if not self._checked:
            self._checked = True
            self._has_context = _has_streamlit_context()
        
        if not self._has_context:
            # Worker mode - вернуть пустой dict-like объект
            return _DummySessionState()
        
        if self._st is None:
            import streamlit
            self._st = streamlit
        return self._st.session_state


class _DummySessionState(dict):
    """Заглушка для session_state в Worker режиме"""
    def __contains__(self, key):
        return False
    
    def __getitem__(self, key):
        return {}  # Возвращаем пустой dict вместо None
    
    def __setitem__(self, key, value):
        pass  # Игнорируем запись
    
    def get(self, key, default=None):
        return default  # Возвращаем default
    
    def keys(self):
        return []


# Глобальный объект для ленивого доступа к streamlit
st = _LazyStreamlit()

load_dotenv()

CACHE_FILE = DATA_DIR / "account_cache.json"

# Lock для thread-safe доступа к файлу кэша
_cache_file_lock = threading.Lock()


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
    # Читаем из файла напрямую (не из session_state) с lock
    with _cache_file_lock:
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
        with _cache_file_lock:
            cached_data = load_json(str(CACHE_FILE), default={})

        st.session_state.account_cache = {
            'main_account': cached_data.get('main_account'),
            'clients': cached_data.get('clients', {}),
            'last_updated': cached_data.get('last_updated')
        }
        logger.debug("Cache initialized")


def refresh_cache_from_file():
    """
    Перезагрузить кэш из файла в session_state.
    Используется когда фоновый поток обновил файл кэша.
    """
    with _cache_file_lock:
        cached_data = load_json(str(CACHE_FILE), default={})

    st.session_state.account_cache = {
        'main_account': cached_data.get('main_account'),
        'clients': cached_data.get('clients', {}),
        'last_updated': cached_data.get('last_updated')
    }
    logger.debug("Cache refreshed from file")


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

        # Вычислить positions_value (сумма market_value всех позиций)
        positions_value = sum(p.market_value for p in positions) if positions else 0

        # Сформировать данные для кэша
        cache_data = {
            'account_number': account_number,
            'account_hash': account_hash,
            'total_value': balances.get('liquidationValue', 0),
            'positions_value': positions_value,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'positions_value': positions_value,
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'price': round(p.market_value / p.quantity, 4) if p.quantity > 0 else 0,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0
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

        # Вычислить positions_value (сумма market_value всех позиций)
        positions_value = sum(p.market_value for p in positions) if positions else 0

        # Сформировать данные для кэша
        cache_data = {
            'client_id': client_id,
            'client_name': client_config.name,
            'account_hash': client_config.account_hash,
            'total_value': balances.get('liquidationValue', 0),
            'positions_value': positions_value,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'positions_value': positions_value,
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
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0
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

    # Удалить файл кэша (с lock)
    with _cache_file_lock:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            logger.debug("Cache file deleted")


def _save_cache_to_file():
    """Сохранить кэш в файл"""

    cache = get_cache()
    with _cache_file_lock:
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
    
    ЛОГИКА "ВСЁ ИЛИ НИЧЕГО":
    - Сначала проверить ВСЕ токены (Main + активные клиенты)
    - Если хотя бы один отсутствует → НЕ обновлять, использовать старый кэш
    - Если все OK → обновить полностью
    """
    # Явно загрузить .env (фоновый поток не видит переменные из main)
    load_dotenv()
    
    logger.debug("Background cache update started")
    
    try:
        from app.core.paths import CONFIG_DIR, TOKEN_PATH
        
        # ═══════════════════════════════════════════════════════════════
        # ШАГ 1: Проверить ВСЕ токены ПЕРЕД обновлением
        # ═══════════════════════════════════════════════════════════════
        missing_tokens = []
        
        # Проверить Main токен
        main_token_file = TOKEN_PATH / "main_tokens.json"
        if not main_token_file.exists():
            missing_tokens.append("Main")
        
        # Проверить токены всех АКТИВНЫХ клиентов
        clients_file = CONFIG_DIR / "clients.json"
        clients_config = load_json(str(clients_file), default={})
        clients_list = clients_config.get('slave_accounts', [])
        
        for client_data in clients_list:
            if not isinstance(client_data, dict):
                continue
            client_id = client_data.get('id')
            if not client_id:
                continue
            # Только активные клиенты
            if not client_data.get('enabled', False):
                continue
            
            client_token_file = TOKEN_PATH / f"{client_id}_tokens.json"
            if not client_token_file.exists():
                client_name = client_data.get('name', client_id)
                missing_tokens.append(client_name)
        
        # Если есть недостающие токены — НЕ обновлять кэш
        if missing_tokens:
            logger.warning(f"⚠️ Missing tokens: {', '.join(missing_tokens)}. Using cached data.")
            return
        
        # ═══════════════════════════════════════════════════════════════
        # ШАГ 2: Все токены OK — обновить кэш
        # ═══════════════════════════════════════════════════════════════
        main_data = _update_main_account_background()
        clients_data = _update_clients_background()
        
        # Проверить что ВСЕ данные получены успешно
        if main_data is None:
            logger.warning("⚠️ Failed to update Main account. Using cached data.")
            return
        
        # Посчитать сколько клиентов должно быть
        expected_clients = sum(1 for c in clients_list if isinstance(c, dict) and c.get('enabled', False))
        
        if clients_data is None or len(clients_data) < expected_clients:
            actual = len(clients_data) if clients_data else 0
            logger.warning(f"⚠️ Not all clients updated ({actual}/{expected_clients}). Using cached data.")
            return
        
        # ═══════════════════════════════════════════════════════════════
        # ШАГ 3: ВСЁ успешно — записать в файл
        # ═══════════════════════════════════════════════════════════════
        with _cache_file_lock:
            cache = {
                'main_account': main_data,
                'clients': clients_data,
                'last_updated': datetime.now().isoformat()
            }
            save_json(str(CACHE_FILE), cache)
        
        # Установить флаг для обновления GUI
        set_cache_updated(True)
        
        # Компактный лог
        main_pos_count = len(main_data.get('positions', []))
        main_equity = main_data.get('total_value', 0)
        equity_str = f"${main_equity/1000:.0f}K" if main_equity >= 1000 else f"${main_equity:.0f}"
        logger.info(f"📊 Cache: Main {main_pos_count} pos/{equity_str}, {len(clients_data)} clients")
            
    except Exception as e:
        logger.error(f"Background: Cache update failed: {e}")


def _update_main_account_background() -> Optional[Dict]:
    """
    Обновить Main Account в фоновом потоке.
    Не использует st.session_state.
    """
    try:
        from app.core.config import get_main_client
        from app.core.paths import TOKEN_PATH
        
        # ═══════════════════════════════════════════════════════════════
        # Проверить существование токена ПЕРЕД созданием Client
        # Иначе schwabdev автоматически откроет браузер для OAuth
        # ═══════════════════════════════════════════════════════════════
        token_file = TOKEN_PATH / "main_tokens.json"
        if not token_file.exists():
            logger.debug("Background: Main token not found, skipping")
            return None
        
        # Получить credentials из .env
        app_key = os.getenv('MAIN_KEY_ID')
        app_secret = os.getenv('MAIN_CLIENT_SECRET')
        account_number = os.getenv('MAIN_ACCOUNT_NUMBER')
        
        if not all([app_key, app_secret, account_number]):
            logger.warning("Background: Main account credentials not found in .env")
            return None
        
        # Получить клиента из кэша (или создать нового)
        client = get_main_client()
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
        
        # Вычислить positions_value (сумма market_value всех позиций)
        positions_value = sum(p.market_value for p in positions) if positions else 0
        
        # Сформировать данные
        # noinspection PyDictCreation
        cache_data = {
            'account_number': account_number,
            'account_hash': account_hash,
            'total_value': balances.get('liquidationValue', 0),
            'positions_value': positions_value,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'positions_value': positions_value,
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'price': round(p.market_value / p.quantity, 4) if p.quantity > 0 else 0,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0
        }
        
        logger.debug(f"Main: {len(positions)} pos, ${balances.get('liquidationValue', 0):,.0f}")
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
        
        logger.debug(f"Background: {len(clients_cache)} clients updated")
        return clients_cache
        
    except Exception as e:
        logger.error(f"Background: Error updating clients: {e}")
        return None


def _update_single_client_background(client_id: str, client_data: Dict) -> Optional[Dict]:
    """
    Обновить одного клиента в фоновом потоке.
    Использует кэшированные клиенты для надёжности.
    """
    try:
        from app.gui.utils.env_manager import load_client_from_env
        from app.core.paths import TOKEN_PATH
        from app.core.config import get_slave_client
        
        # ═══════════════════════════════════════════════════════════════
        # Проверить существование токена ПЕРЕД созданием Client
        # Иначе schwabdev автоматически откроет браузер для OAuth
        # ═══════════════════════════════════════════════════════════════
        token_file = TOKEN_PATH / f"{client_id}_tokens.json"
        if not token_file.exists():
            logger.debug(f"Background: Token for {client_id} not found, skipping")
            return None
        
        env_data = load_client_from_env(client_id)
        
        if not all([env_data.get('key_id'), env_data.get('client_secret')]):
            logger.warning(f"Background: Client {client_id} credentials not found")
            return None
        
        # Использовать кэшированного клиента (или создать нового)
        slave_client = get_slave_client(
            client_id,
            env_data['key_id'],
            env_data['client_secret'],
            env_data.get('redirect_uri', 'https://127.0.0.1:8182')
        )
        
        if not slave_client:
            logger.warning(f"Background: Could not get client for {client_id}")
            return None
        
        account_hash = client_data.get('account_hash')
        if not account_hash:
            logger.warning(f"Background: Client {client_id} account_hash not found")
            return None
        
        # Получить данные из API
        details = slave_client.account_details(account_hash, fields='positions').json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = parse_positions_from_account_details(details)
        
        # Вычислить positions_value (сумма market_value всех позиций)
        positions_value = sum(p.market_value for p in positions) if positions else 0
        
        cache_data = {
            'client_id': client_id,
            'client_name': client_data.get('name', client_id),
            'account_hash': account_hash,
            'total_value': balances.get('liquidationValue', 0),
            'positions_value': positions_value,
            'balances': {
                'liquidation_value': balances.get('liquidationValue', 0),
                'positions_value': positions_value,
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'available_funds': balances.get('availableFunds', 0),
            },
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'price': round(p.market_value / p.quantity, 4) if p.quantity > 0 else 0,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl
                }
                for p in positions
            ],
            'positions_count': len(positions),
            'total_pl': sum(p.unrealized_pl for p in positions) if positions else 0
        }
        
        logger.debug(f"Client {client_id}: {len(positions)} positions")
        return cache_data
        
    except Exception as e:
        logger.error(f"Background: Error updating client {client_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# SIMULATION (DRY RUN) CACHE
# ═══════════════════════════════════════════════════════════════

# Файл для хранения simulation cache
SIMULATION_CACHE_FILE = DATA_DIR / "account_cache_dry.json"

# Lock для simulation cache
_simulation_cache_lock = threading.Lock()


def init_simulation_cache():
    """
    Инициализировать simulation cache из реального кэша.
    Используется при Manual Sync в SIMULATION режиме (с чистого листа).
    
    1. Обнуляет slave_*_history_dry.json для всех клиентов
    2. Копирует account_cache.json в account_cache_dry.json
    """
    from app.core.paths import CONFIG_DIR, get_client_history_dry_file
    
    # ═══════════════════════════════════════════════════════════════
    # ШАГ 1: Обнулить все slave_*_history_dry.json
    # ═══════════════════════════════════════════════════════════════
    clients_file = CONFIG_DIR / "clients.json"
    clients_config = load_json(str(clients_file), default={})
    clients_list = clients_config.get('slave_accounts', [])
    
    for client_data in clients_list:
        if not isinstance(client_data, dict):
            continue
        client_id = client_data.get('id')
        if not client_id:
            continue
        
        # Обнулить history_dry для каждого клиента
        history_dry_file = get_client_history_dry_file(client_id)
        save_json(str(history_dry_file), [])
        logger.debug(f"Cleared {client_id}_history_dry.json")
    
    # ═══════════════════════════════════════════════════════════════
    # ШАГ 2: Скопировать account_cache.json в account_cache_dry.json
    # ═══════════════════════════════════════════════════════════════
    with _cache_file_lock:
        real_cache = load_json(str(CACHE_FILE), default={
            'main_account': None,
            'clients': {},
            'last_updated': None
        })
    
    # Копировать структуру из реального кэша
    simulation_cache = {
        'main_account': real_cache.get('main_account'),
        'clients': real_cache.get('clients', {}),
        'last_updated': datetime.now().isoformat(),
        'is_simulation': True
    }
    
    with _simulation_cache_lock:
        save_json(str(SIMULATION_CACHE_FILE), simulation_cache)
    
    logger.debug("Simulation cache initialized from real cache")


def get_simulation_cache() -> Dict:
    """
    Получить simulation cache.
    
    Returns:
        Dict с simulation данными
    """
    with _simulation_cache_lock:
        cache = load_json(str(SIMULATION_CACHE_FILE), default={
            'main_account': None,
            'clients': {},
            'last_updated': None,
            'is_simulation': True
        })
    return cache


def update_simulation_cache(cache_data: Dict):
    """
    Обновить simulation cache.
    
    Args:
        cache_data: Новые данные кэша
    """
    cache_data['last_updated'] = datetime.now().isoformat()
    cache_data['is_simulation'] = True
    
    with _simulation_cache_lock:
        save_json(str(SIMULATION_CACHE_FILE), cache_data)
    
    logger.debug("Simulation cache updated")


def update_dry_cache_prices():
    """
    Обновить цены и P&L в simulation cache из реальных данных.
    Позиции остаются симулированными, но цены актуальные.
    """
    # Получить реальные цены из реального кэша
    with _cache_file_lock:
        real_cache = load_json(str(CACHE_FILE), default={})
    
    # Получить simulation cache
    with _simulation_cache_lock:
        sim_cache = load_json(str(SIMULATION_CACHE_FILE), default={
            'main_account': None,
            'clients': {},
            'last_updated': None,
            'is_simulation': True
        })
    
    # Построить карту цен из реального кэша
    real_prices = {}
    
    # Main account prices
    main_account = real_cache.get('main_account', {})
    if main_account:
        for pos in main_account.get('positions', []):
            symbol = pos.get('symbol')
            price = pos.get('price', 0)
            if symbol and price > 0:
                real_prices[symbol] = price
    
    # Clients prices
    for client_id, client_data in real_cache.get('clients', {}).items():
        for pos in client_data.get('positions', []):
            symbol = pos.get('symbol')
            price = pos.get('price', 0)
            if symbol and price > 0:
                real_prices[symbol] = price
    
    # Обновить цены в simulation cache для клиентов
    for client_id, client_data in sim_cache.get('clients', {}).items():
        if not client_data:
            continue
        
        total_pl = 0
        for pos in client_data.get('positions', []):
            symbol = pos.get('symbol')
            if symbol in real_prices:
                new_price = real_prices[symbol]
                quantity = pos.get('quantity', 0)
                old_market_value = pos.get('market_value', 0)
                
                # Обновить цену и market value
                pos['price'] = new_price
                pos['market_value'] = round(new_price * quantity, 2)
                
                # Пересчитать P&L (примерно)
                # Используем cost_basis если есть, иначе оставляем как есть
                cost_basis = pos.get('cost_basis', old_market_value)
                pos['unrealized_pl'] = round(pos['market_value'] - cost_basis, 2)
                total_pl += pos['unrealized_pl']
        
        client_data['total_pl'] = round(total_pl, 2)
    
    sim_cache['last_updated'] = datetime.now().isoformat()
    
    with _simulation_cache_lock:
        save_json(str(SIMULATION_CACHE_FILE), sim_cache)
    
    logger.debug(f"Dry cache prices updated from {len(real_prices)} real prices")


# ═══════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ WORKER (без Streamlit)
# ═══════════════════════════════════════════════════════════════

def update_all_cache_for_worker():
    """
    Обновить кэш из Worker (без Streamlit).
    Алиас для update_all_cache_background().
    """
    update_all_cache_background()


# ═══════════════════════════════════════════════════════════════
# PUBLIC WRAPPERS FOR WORKER
# ═══════════════════════════════════════════════════════════════

def update_main_account_for_worker():
    """
    Публичная обёртка для _update_main_account_background.
    Используется в sync_worker.py.
    """
    return _update_main_account_background()


def update_clients_for_worker():
    """
    Публичная обёртка для _update_clients_background.
    Используется в sync_worker.py.
    """
    return _update_clients_background()


def get_cache_file_lock():
    """
    Публичный доступ к блокировке файла кэша.
    Используется в sync_worker.py.
    """
    return _cache_file_lock