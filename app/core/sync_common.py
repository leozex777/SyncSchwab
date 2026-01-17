# app/core/sync_common.py
"""
Общие функции для всех режимов синхронизации.

Используются в:
- modes/live/
- modes/simulation/
- modes/monitor_live/
- modes/monitor_simulation/
"""

from typing import Dict, List, Optional
from datetime import datetime
import schwabdev

from app.core.logger import logger
from app.core.json_utils import load_json, save_json
from app.core.config_cache import ConfigCache
from app.core.paths import (
    DATA_DIR,
    get_client_history_file,
    get_client_history_dry_file
)
from app.models.copier.entities import parse_positions_from_account_details


# ═══════════════════════════════════════════════════════════════
# ИСКЛЮЧЕНИЯ
# ═══════════════════════════════════════════════════════════════

class InvalidAccountHashError(Exception):
    """Ошибка невалидного account_hash"""
    pass


# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════

def get_notification_settings() -> dict:
    """Получить настройки уведомлений из конфига (через кэш)"""
    settings = ConfigCache.get_general_settings()
    notifications = settings.get('notifications', {})
    
    return {
        'toast_on_error': notifications.get('toast_on_error', True),
        'toast_on_success': notifications.get('toast_on_success', False),
        'sound_on_error': notifications.get('sound_on_error', True),
        'telegram_enabled': notifications.get('telegram_enabled', False),
        'telegram_bot_token': notifications.get('telegram_bot_token', ''),
        'telegram_chat_id': notifications.get('telegram_chat_id', '')
    }


def play_error_sound():
    """Воспроизвести звук ошибки"""
    try:
        import platform
        if platform.system() == 'Windows':
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        else:
            print('\a', end='', flush=True)
    except Exception as e:
        logger.debug(f"Could not play error sound: {e}")


# ═══════════════════════════════════════════════════════════════
# ПРОВЕРКА ОШИБОК HASH
# ═══════════════════════════════════════════════════════════════

def is_invalid_hash_error(response) -> bool:
    """Проверить является ли ответ ошибкой invalid hash"""
    try:
        if hasattr(response, 'status_code'):
            if response.status_code in [400, 401, 403, 404]:
                text = response.text.lower() if hasattr(response, 'text') else ''
                if any(word in text for word in ['invalid', 'hash', 'account', 'not found']):
                    return True
        return False
    except (AttributeError, TypeError, ValueError):
        return False


def is_hash_error_message(error_msg: str) -> bool:
    """Проверить содержит ли сообщение об ошибке указание на invalid hash"""
    error_lower = error_msg.lower()
    keywords = ['invalid account', 'account not found', 'invalid hash', 'bad request', 'unauthorized']
    return any(keyword in error_lower for keyword in keywords)


# ═══════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ ДАННЫХ ИЗ API
# ═══════════════════════════════════════════════════════════════

def get_positions(
    client: schwabdev.Client,
    account_hash: str,
    label: str = "Account"
) -> List:
    """
    Получить позиции аккаунта из API.
    
    Args:
        client: schwabdev.Client
        account_hash: Hash аккаунта
        label: Метка для логирования (Main, Slave, etc.)
        
    Returns:
        List[Position]
        
    Raises:
        InvalidAccountHashError: Если hash невалидный
    """
    logger.debug(f"Getting {label} positions...")
    
    try:
        response = client.account_details(account_hash, fields='positions')
        
        if is_invalid_hash_error(response):
            logger.error(f"❌ Invalid account hash for {label}")
            raise InvalidAccountHashError(f"Invalid account hash for {label}")
        
        details = response.json()
        positions = parse_positions_from_account_details(details)
        
        logger.debug(f"{label}: {len(positions)} positions")
        return positions
        
    except InvalidAccountHashError:
        raise
    except Exception as e:
        if is_hash_error_message(str(e)):
            raise InvalidAccountHashError(f"Invalid account hash for {label}: {e}")
        raise


def get_equity(
    client: schwabdev.Client,
    account_hash: str,
    label: str = "Account"
) -> float:
    """
    Получить equity (liquidationValue) аккаунта из API.
    
    Args:
        client: schwabdev.Client
        account_hash: Hash аккаунта
        label: Метка для логирования
        
    Returns:
        float: Equity (liquidationValue)
        
    Raises:
        InvalidAccountHashError: Если hash невалидный
    """
    try:
        response = client.account_details(account_hash)
        
        if is_invalid_hash_error(response):
            raise InvalidAccountHashError(f"Invalid account hash for {label}")
        
        details = response.json()
        sa = details.get('securitiesAccount', {})
        equity = sa.get('currentBalances', {}).get('liquidationValue', 0)
        
        logger.debug(f"{label} Equity: ${equity:,.2f}")
        return equity
        
    except InvalidAccountHashError:
        raise
    except Exception as e:
        if is_hash_error_message(str(e)):
            raise InvalidAccountHashError(f"Invalid account hash for {label}: {e}")
        raise


def get_available_cash(
    client: schwabdev.Client,
    account_hash: str,
    config: Dict = None
) -> float:
    """
    Получить доступные средства с учетом настроек маржи.
    
    Логика:
    1. Если buyingPower = 0 → использовать cashBalance
    2. Если buyingPower > 0 и use_margin = False → cashBalance
    3. Если buyingPower > 0 и use_margin = True:
       - user_limit = totalValue * (1 + margin_percent/100)
       - max_allowed = min(buyingPower, user_limit)
       - available = max(0, max_allowed - positions_value)
       
    Args:
        client: schwabdev.Client
        account_hash: Hash аккаунта
        config: Конфигурация клиента (для настроек маржи)
        
    Returns:
        float: Доступные средства
    """
    config = config or {}
    
    try:
        response = client.account_details(account_hash, fields='positions')
        
        if is_invalid_hash_error(response):
            raise InvalidAccountHashError("Invalid account hash for slave")
        
        details = response.json()
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        
        buying_power = balances.get('buyingPower', 0)
        cash_balance = balances.get('cashBalance', 0)
        total_value = balances.get('liquidationValue', 0)
        
        # Рассчитать positions_value
        positions = sa.get('positions', [])
        positions_value = sum(p.get('marketValue', 0) for p in positions)
        
        logger.debug(f"Balances: Total=${total_value:,.0f}, Cash=${cash_balance:,.0f}, BP=${buying_power:,.0f}")
        
        # СЛУЧАЙ 1: buyingPower = 0 (Cash Account без маржи)
        if buying_power == 0:
            available = cash_balance
            logger.debug(f"Using cashBalance: ${available:,.0f}")
            return available
        
        # СЛУЧАЙ 2: buyingPower > 0
        use_margin = config.get('use_margin', False)
        margin_percent = config.get('margin_percent', 0)
        
        # Проверить разрешение маржи от Schwab
        schwab_allows_margin = buying_power > cash_balance * 1.1
        
        if not use_margin:
            available = cash_balance
            logger.debug(f"Margin disabled, using cashBalance: ${available:,.0f}")
        
        elif use_margin and not schwab_allows_margin:
            available = cash_balance
            logger.warning(f"⚠️ Margin requested but NOT available from Schwab")
        
        elif use_margin and schwab_allows_margin and margin_percent > 0:
            user_limit = total_value * (1 + margin_percent / 100)
            max_allowed = min(buying_power, user_limit)
            available = max(0.0, max_allowed - positions_value)
            logger.debug(f"Margin {margin_percent}%: Available ${available:,.0f}")
        
        else:
            available = cash_balance
        
        return available
        
    except InvalidAccountHashError:
        raise
    except Exception as e:
        if is_hash_error_message(str(e)):
            raise InvalidAccountHashError(f"Invalid account hash: {e}")
        raise


def get_prices(positions: List) -> Dict[str, float]:
    """
    Получить цены из позиций.
    
    Args:
        positions: List[Position]
        
    Returns:
        Dict {symbol: price}
    """
    prices = {}
    for pos in positions:
        prices[pos.symbol] = pos.average_price
    return prices


# ═══════════════════════════════════════════════════════════════
# ФОРМИРОВАНИЕ РЕЗУЛЬТАТА
# ═══════════════════════════════════════════════════════════════

def build_sync_result(
    operating_mode: str,
    scale: float,
    main_equity: float,
    slave_equity: float,
    deltas: Dict,
    valid_deltas: Dict,
    results: List,
    status: str,
    errors: List = None
) -> Dict:
    """
    Собрать результат синхронизации.
    
    Args:
        operating_mode: Режим работы (simulation, live, etc.)
        scale: Коэффициент масштабирования
        main_equity: Equity главного аккаунта
        slave_equity: Equity клиентского аккаунта
        deltas: Все дельты
        valid_deltas: Валидные дельты после проверок
        results: Результаты выполнения ордеров
        status: Статус синхронизации
        errors: Список ошибок
        
    Returns:
        Dict с результатом синхронизации
    """
    return {
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'operating_mode': operating_mode,
        'scale': scale,
        'main_equity': main_equity,
        'slave_equity': slave_equity,
        'deltas': deltas,
        'valid_deltas': valid_deltas,
        'results': results,
        'errors': errors or [],
        'summary': {
            'total_deltas': len(deltas),
            'orders_placed': len(results),
            'orders_success': sum(1 for r in results if r.get('status') in ['SUCCESS', 'DRY_RUN', 'SIMULATED']),
            'orders_failed': sum(1 for r in results if r.get('status') == 'ERROR')
        }
    }


# ═══════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ ИСТОРИИ
# ═══════════════════════════════════════════════════════════════

def get_history_file_path(client_id: str, operating_mode: str) -> str:
    """
    Получить путь к файлу истории в зависимости от режима.
    
    Args:
        client_id: ID клиента (например: slave_1)
        operating_mode: Режим работы
        
    Returns:
        Путь к файлу истории
    """
    if operating_mode in ('dry_run', 'simulation'):
        return str(get_client_history_dry_file(client_id))
    else:
        return str(get_client_history_file(client_id))


def save_sync_result(
    result: Dict,
    client_id: str,
    operating_mode: str
):
    """
    Сохранить результат синхронизации в соответствующий файл.
    
    LIVE Mode: записывать только если были реальные ордера
    DRY RUN / SIMULATION: записывать всегда
    
    Args:
        result: Результат синхронизации
        client_id: ID клиента
        operating_mode: Режим работы
    """
    # LIVE Mode: пропустить если не было ордеров
    if operating_mode == 'live':
        orders = result.get('results', [])
        if not orders:
            logger.info("[SYNC] 📝 History write skipped (LIVE: no orders executed)")
            return
    
    history_file = get_history_file_path(client_id, operating_mode)
    
    try:
        history = load_json(history_file, default=[])
        history.append(result)
        
        if operating_mode in ('dry_run', 'simulation'):
            # DRY RUN / SIMULATION: ограничить до 50 записей
            if len(history) > 50:
                history = history[-50:]
        # LIVE: хранить всё
        
        save_json(history_file, history)
        
        # Обновить кэш для LIVE режима
        if operating_mode == 'live':
            ConfigCache.update_history(client_id, history)
        
        mode_str = operating_mode.upper()
        logger.info(f"[SYNC] 💾 Results saved to {history_file} ({mode_str})")
        
    except Exception as e:
        logger.error(f"❌ Failed to save results: {e}")


# ═══════════════════════════════════════════════════════════════
# ОБНОВЛЕНИЕ КЭША
# ═══════════════════════════════════════════════════════════════

def update_account_cache_after_sync(
    client_id: str,
    main_positions: List,
    slave_positions: List,
    main_equity: float,
    slave_equity: float
):
    """
    Обновить account_cache.json после синхронизации.
    
    Использует данные уже полученные в sync() чтобы не делать
    дополнительных API вызовов.
    
    Args:
        client_id: ID клиента
        main_positions: Позиции главного аккаунта
        slave_positions: Позиции клиентского аккаунта
        main_equity: Equity главного аккаунта
        slave_equity: Equity клиентского аккаунта
    """
    try:
        cache_file = DATA_DIR / "account_cache.json"
        cache = load_json(str(cache_file), default={})
        
        # Обновить Main Account
        if cache.get('main_account'):
            cache['main_account']['positions'] = [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': getattr(p, 'market_value', 0),
                    'unrealized_pl': getattr(p, 'unrealized_pl', 0)
                }
                for p in main_positions
            ]
            cache['main_account']['positions_count'] = len(main_positions)
            cache['main_account']['balances']['liquidation_value'] = main_equity
        
        # Обновить Slave (текущий клиент)
        if client_id and cache.get('clients', {}).get(client_id):
            cache['clients'][client_id]['positions'] = [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'market_value': getattr(p, 'market_value', 0),
                    'unrealized_pl': getattr(p, 'unrealized_pl', 0)
                }
                for p in slave_positions
            ]
            cache['clients'][client_id]['positions_count'] = len(slave_positions)
            cache['clients'][client_id]['balances']['liquidation_value'] = slave_equity
        
        # Обновить timestamp
        cache['last_updated'] = datetime.now().isoformat()
        
        # Сохранить
        save_json(str(cache_file), cache)
        
        # Установить флаг для автообновления GUI
        from app.core.cache_manager import set_cache_updated
        set_cache_updated(True)
        
        logger.debug(f"[SYNC] Cache updated after sync")
        
    except Exception as e:
        logger.warning(f"[SYNC] Could not update cache after sync: {e}")


# ═══════════════════════════════════════════════════════════════
# ИЗВЛЕЧЕНИЕ ORDER ID
# ═══════════════════════════════════════════════════════════════

def extract_order_id(response) -> Optional[str]:
    """
    Извлечь order ID из ответа Schwab API.
    
    Args:
        response: Ответ от API
        
    Returns:
        Order ID или None
    """
    try:
        location = response.headers.get('Location', '')
        if '/orders/' in location:
            return location.split('/orders/')[-1]
    except AttributeError:
        pass
    except Exception as e:
        logger.warning(f"Could not extract order ID: {e}")
    return None
