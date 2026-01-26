#!/usr/bin/env python3
"""
sync_worker.py - Отдельный процесс для Auto Sync

Работает независимо от Streamlit GUI.
Общается с GUI через файлы в config/.

Запуск:
    python sync_worker.py

Управление:
    GUI записывает в config/worker_status.json:
    - {"command": "start"} → worker начинает синхронизацию
    - {"command": "stop"}  → worker останавливается
"""

import os
import sys

import time
import signal
import ctypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from dotenv import load_dotenv

from app.core.logger import logger, setup_logger
from app.core.json_utils import load_json, save_json
from app.core.paths import CONFIG_DIR, TOKEN_PATH

# ═══════════════════════════════════════════════════════════════
# Установить Worker mode ДО любых импортов
# ═══════════════════════════════════════════════════════════════
os.environ['SYNC_WORKER_MODE'] = '1'

# Добавить корневую директорию в путь
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Теперь можно импортировать модули проекта
load_dotenv()

# ═══════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ═══════════════════════════════════════════════════════════════

WORKER_STATUS_FILE = CONFIG_DIR / "worker_status.json"
GUI_STATUS_FILE = CONFIG_DIR / "gui_status.json"
GENERAL_SETTINGS_FILE = CONFIG_DIR / "general_settings.json"
SYNC_SETTINGS_FILE = CONFIG_DIR / "sync_settings.json"
CLIENTS_FILE = CONFIG_DIR / "clients.json"
CURRENT_DELTA_FILE = Path("data/clients/current_delta.json")

HEARTBEAT_INTERVAL = 30  # секунд
CHECK_COMMAND_INTERVAL = 5  # секунд между проверками команды


def get_et_time_str() -> str:
    """Получить текущее время в ET (Eastern Time)"""
    try:
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        return et_now.strftime("%H:%M ET")
    except ImportError:
        # Если pytz не установлен, используем приблизительный расчёт
        # ET = UTC - 5 (или UTC - 4 летом)
        utc_now = datetime.utcnow()
        et_now = utc_now - timedelta(hours=5)
        return et_now.strftime("%H:%M ET")

# ═══════════════════════════════════════════════════════════════
# PREVENT SLEEP (Windows) - для Modern Standby (S0)
# ═══════════════════════════════════════════════════════════════


# Константы для SetThreadExecutionState
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_AWAYMODE_REQUIRED = 0x00000040  # Критично для S0!


def prevent_sleep(log: bool = True):
    """
    Запретить компьютеру засыпать (Windows).
    Использует ES_AWAYMODE_REQUIRED для Modern Standby (S0).
    """
    if sys.platform != 'win32':
        return
    
    try:
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        # Away Mode позволяет системе думать что она в спячке, но продолжать выполнять код
        # noinspection PyUnresolvedReferences
        result = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        )
        if log:
            if result:
                logger.info("[WORKER] Sleep prevention enabled (AwayMode)")
            else:
                logger.warning("[WORKER] SetThreadExecutionState returned 0")
    except (OSError, AttributeError) as e:
        logger.warning(f"[WORKER] Could not prevent sleep: {e}")


def ping_prevent_sleep():
    """
    Периодический 'пинг' для Modern Standby (S0).
    Вызывать каждые несколько секунд пока Worker работает.
    """
    if sys.platform != 'win32':
        return
    
    try:
        # Повторный вызов с теми же флагами
        # noinspection PyUnresolvedReferences
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        )
    except (OSError, AttributeError):
        pass


def allow_sleep():
    """Разрешить компьютеру засыпать (Windows)"""
    if sys.platform != 'win32':
        return
    
    try:
        # Сбросить на стандартное поведение
        # noinspection PyUnresolvedReferences
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        logger.info("[WORKER] Sleep prevention disabled")
    except (OSError, AttributeError) as e:
        logger.warning(f"[WORKER] Could not allow sleep: {e}")


# ═══════════════════════════════════════════════════════════════
# WORKER STATUS
# ═══════════════════════════════════════════════════════════════


def is_process_alive(pid: int) -> bool:
    """Проверить жив ли процесс по PID"""
    if pid is None:
        return False
    try:
        if sys.platform == 'win32':
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def cleanup_stale_status():
    """
    Проверить и сбросить статус если старый процесс мёртв.
    Вызывается при старте Worker.
    """
    status = load_worker_status()
    old_pid = status.get("pid")
    old_command = status.get("command")
    
    # Если был command=start, но процесс мёртв — сбросить
    if old_command == "start" and old_pid:
        if not is_process_alive(old_pid):
            logger.info(f"[WORKER] Stale status detected (old PID {old_pid} is dead), resetting to stop")
            status["command"] = "stop"
            status["running"] = False
            status["pid"] = None
            save_worker_status(status)


def is_gui_alive() -> bool:
    """
    Проверить жив ли GUI процесс.
    Читает PID из gui_status.json и проверяет процесс.
    """
    try:
        gui_status = load_json(GUI_STATUS_FILE, default={})
        gui_pid = gui_status.get("pid")
        if gui_pid is None:
            return False
        return is_process_alive(gui_pid)
    except (OSError, ValueError, KeyError):
        return False


def load_worker_status() -> Dict:
    """Загрузить статус worker"""
    default = {
        "command": "stop",
        "running": False,
        "started_at": None,
        "last_heartbeat": None,
        "last_sync": None,
        "last_sync_result": None,
        "interval_seconds": 60,
        "pid": None,
        "error": None
    }
    return load_json(WORKER_STATUS_FILE, default=default)


def save_worker_status(status: Dict):
    """Сохранить статус worker"""
    save_json(WORKER_STATUS_FILE, status)


def update_heartbeat(status: Dict):
    """Обновить heartbeat"""
    status["last_heartbeat"] = datetime.now().isoformat()
    status["pid"] = os.getpid()
    save_worker_status(status)


def set_worker_running(running: bool, error: str = None):
    """Установить статус running"""
    status = load_worker_status()
    status["running"] = running
    status["pid"] = os.getpid() if running else None
    status["error"] = error
    if running:
        status["started_at"] = datetime.now().isoformat()
    save_worker_status(status)

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════


def get_operating_mode() -> str:
    """Получить режим работы из general_settings.json"""
    settings = load_json(GENERAL_SETTINGS_FILE, default={})
    return settings.get("operating_mode", "monitor")


def get_monitor_sync_mode() -> str:
    """Получить под-режим Monitor (live или simulation) из general_settings.json"""
    settings = load_json(GENERAL_SETTINGS_FILE, default={})
    return settings.get("monitor_sync_mode", "live")


def get_sync_interval_seconds() -> int:
    """Получить интервал синхронизации в секундах"""
    settings = load_json(SYNC_SETTINGS_FILE, default={})
    interval_str = settings.get("auto_sync_interval", "Every 1 minute")
    
    # Парсинг строки интервала
    intervals = {
        "Every 1 minute": 60,
        "Every 2 minutes": 120,
        "Every 5 minutes": 300,
        "Every 10 minutes": 600,
        "Every 15 minutes": 900,
        "Every 30 minutes": 1800,
    }
    return intervals.get(interval_str, 60)


def get_enabled_clients() -> List[Dict]:
    """Получить список enabled клиентов из clients.json"""
    data = load_json(CLIENTS_FILE, default={})
    slaves = data.get("slave_accounts", [])
    return [s for s in slaves if s.get("enabled", False)]


def get_main_account() -> Dict:
    """Получить main account из clients.json"""
    data = load_json(CLIENTS_FILE, default={})
    return data.get("main_account", {})


def update_gui_sync_status():
    """
    Обновить sync_settings.json для GUI таймера.
    Вызывается после каждой успешной синхронизации.
    """
    try:
        settings = load_json(SYNC_SETTINGS_FILE, default={})
        
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        # Обновить время последней синхронизации
        settings['last_sync_time'] = now.isoformat()
        
        # Вычислить время следующей синхронизации
        interval_seconds = get_sync_interval_seconds()
        next_sync = now + timedelta(seconds=interval_seconds)
        settings['next_sync_time'] = next_sync.isoformat()
        
        # Обновить счётчик за день
        if settings.get('syncs_today_date') != today_str:
            settings['syncs_today'] = 1
            settings['syncs_today_date'] = today_str
        else:
            settings['syncs_today'] = settings.get('syncs_today', 0) + 1
        
        save_json(SYNC_SETTINGS_FILE, settings)
        
    except Exception as e:
        logger.debug(f"[WORKER] Error updating GUI sync status: {e}")


def init_gui_sync_timer():
    """
    Инициализировать таймер GUI при старте.
    Устанавливает next_sync_time на текущее время + interval.
    """
    try:
        settings = load_json(SYNC_SETTINGS_FILE, default={})
        
        now = datetime.now()
        interval_seconds = get_sync_interval_seconds()
        next_sync = now + timedelta(seconds=interval_seconds)
        
        settings['next_sync_time'] = next_sync.isoformat()
        # Не меняем last_sync_time и syncs_today при старте
        
        save_json(SYNC_SETTINGS_FILE, settings)
        
    except Exception as e:
        logger.debug(f"[WORKER] Error initializing GUI sync timer: {e}")


def reset_gui_sync_timer():
    """
    Сбросить таймер GUI при остановке.
    Очищает next_sync_time.
    """
    try:
        settings = load_json(SYNC_SETTINGS_FILE, default={})
        
        settings['next_sync_time'] = None
        # Не трогаем last_sync_time и syncs_today — это история
        
        save_json(SYNC_SETTINGS_FILE, settings)
        
    except Exception as e:
        logger.debug(f"[WORKER] Error resetting GUI sync timer: {e}")


# ═══════════════════════════════════════════════════════════════
# MARKET HOURS
# ═══════════════════════════════════════════════════════════════


def is_market_open() -> tuple:
    """
    Проверить открыт ли рынок.
    
    Читает настройки из sync_settings.json:
    - auto_sync_market_hours: True = 9:30-16:00
    - auto_sync_start_time / auto_sync_end_time: кастомное время
    
    Учитывает праздники и early close из market_calendar.json.
    
    Returns:
        (is_open: bool, reason: str)
    """
    import pytz
    from datetime import time as dt_time
    
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    today_str = now.strftime('%Y-%m-%d')
    
    # ═══════════════════════════════════════════════════════════════
    # 1. Проверка выходных
    # ═══════════════════════════════════════════════════════════════
    if now.weekday() >= 5:
        day_name = "Saturday" if now.weekday() == 5 else "Sunday"
        return False, f"Weekend ({day_name})"
    
    # ═══════════════════════════════════════════════════════════════
    # 2. Загрузить календарь
    # ═══════════════════════════════════════════════════════════════
    calendar_file = CONFIG_DIR / "market_calendar.json"
    calendar = load_json(str(calendar_file), default={})
    
    # ═══════════════════════════════════════════════════════════════
    # 3. Проверка праздников
    # ═══════════════════════════════════════════════════════════════
    holidays = calendar.get('holidays', [])
    for holiday in holidays:
        if holiday.get('date') == today_str:
            holiday_name = holiday.get('name', 'Holiday')
            return False, f"Holiday ({holiday_name})"
    
    # ═══════════════════════════════════════════════════════════════
    # 4. Определить время закрытия (early close или обычное)
    # ═══════════════════════════════════════════════════════════════
    close_time_str = "16:00"
    early_close_name = None
    
    early_closes = calendar.get('early_close', [])
    for early in early_closes:
        if early.get('date') == today_str:
            close_time_str = early.get('close_time', '13:00')
            early_close_name = early.get('name', 'Early Close')
            break
    
    # ═══════════════════════════════════════════════════════════════
    # 5. Загрузить настройки Active Hours
    # ═══════════════════════════════════════════════════════════════
    settings = load_json(str(SYNC_SETTINGS_FILE), default={})
    
    market_hours_enabled = settings.get('auto_sync_market_hours', True)
    
    # Время открытия
    if market_hours_enabled:
        open_time_str = "09:30"
    else:
        open_time_str = settings.get('auto_sync_start_time', '09:30')
    
    # Время закрытия (early close имеет приоритет)
    if early_close_name:
        pass  # close_time_str уже установлен выше
    elif market_hours_enabled:
        close_time_str = "16:00"
    else:
        close_time_str = settings.get('auto_sync_end_time', '16:00')
    
    logger.debug(f"[MARKET] market_hours_enabled={market_hours_enabled}, open={open_time_str}, close={close_time_str}")
    
    # ═══════════════════════════════════════════════════════════════
    # 6. Проверка времени
    # ═══════════════════════════════════════════════════════════════
    try:
        open_time = datetime.strptime(open_time_str, "%H:%M").time()
        close_time = datetime.strptime(close_time_str, "%H:%M").time()
        current_time = now.time()
        
        if current_time < open_time:
            return False, f"Before market open ({open_time_str} ET)"
        
        if current_time > close_time:
            if early_close_name:
                return False, f"After early close ({close_time_str} ET - {early_close_name})"
            else:
                return False, f"After market close ({close_time_str} ET)"
        
        return True, "Market open"
        
    except ValueError as e:
        logger.error(f"[WORKER] Error parsing time: {e}")
        # Fallback к стандартным часам
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        current_time = now.time()
        
        if current_time < market_open:
            return False, f"Before market open ({current_time.strftime('%H:%M')} ET)"
        if current_time > market_close:
            return False, f"After market close ({current_time.strftime('%H:%M')} ET)"
        
        return True, "Market open"

# ═══════════════════════════════════════════════════════════════
# SCHWAB CLIENTS (с кэшированием)
# ═══════════════════════════════════════════════════════════════


_main_client = None
_slave_clients: Dict = {}


def get_main_client():
    """Получить main client (с кэшированием)"""
    global _main_client
    
    if _main_client is not None:
        return _main_client
    
    import schwabdev
    
    main_key_id = os.getenv('MAIN_KEY_ID')
    main_client_secret = os.getenv('MAIN_CLIENT_SECRET')
    main_redirect_uri = os.getenv('MAIN_REDIRECT_URI', 'https://127.0.0.1:8182')
    
    if not all([main_key_id, main_client_secret]):
        logger.error("[WORKER] Main account credentials not found in .env")
        return None
    
    token_file = TOKEN_PATH / "main_tokens.json"
    if not token_file.exists():
        logger.error("[WORKER] Main account token not found")
        return None
    
    try:
        _main_client = schwabdev.Client(
            app_key=main_key_id,
            app_secret=main_client_secret,
            callback_url=main_redirect_uri,
            tokens_file=str(token_file),
            capture_callback=True
        )
        logger.info("[WORKER] Main client created (cached)")
        return _main_client
    except Exception as e:
        logger.error(f"[WORKER] Failed to create main client: {e}")
        return None


def get_slave_client(client_id: str):
    """Получить slave client (с кэшированием)"""
    global _slave_clients
    
    if client_id in _slave_clients:
        return _slave_clients[client_id]
    
    import schwabdev
    
    # Читаем credentials из .env
    prefix = client_id.upper().replace("-", "_")
    app_key = os.getenv(f'{prefix}_KEY_ID')
    app_secret = os.getenv(f'{prefix}_CLIENT_SECRET')
    callback_url = os.getenv(f'{prefix}_REDIRECT_URI', 'https://127.0.0.1:8182')
    
    if not all([app_key, app_secret]):
        logger.error(f"[WORKER] Credentials not found for {client_id}")
        return None
    
    token_file = TOKEN_PATH / f"{client_id}_tokens.json"
    if not token_file.exists():
        logger.error(f"[WORKER] Token not found for {client_id}")
        return None
    
    try:
        client = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file),
            capture_callback=True
        )
        _slave_clients[client_id] = client
        logger.info(f"[WORKER] Slave client created for {client_id} (cached)")
        return client
    except Exception as e:
        logger.error(f"[WORKER] Failed to create slave client {client_id}: {e}")
        return None


def clear_client_cache():
    """Очистить кэш клиентов (при ошибках или при Start)"""
    global _main_client, _slave_clients
    _main_client = None
    _slave_clients = {}
    logger.debug("[WORKER] Client cache cleared")

# ═══════════════════════════════════════════════════════════════
# СИНХРОНИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════


def perform_sync() -> Dict:
    """
    Выполнить синхронизацию.
    
    Returns:
        Dict с результатом
    """
    from app.core.config_cache import get_clients_from_file
    
    operating_mode = get_operating_mode()
    
    # Получить main client
    main_client = get_main_client()
    if not main_client:
        return {"status": "error", "reason": "main_client_not_available"}
    
    # Читаем клиентов напрямую из файла (не через session_state)
    clients_data = get_clients_from_file()
    
    # Получить main account hash
    main_account = clients_data.get('main_account', {})
    main_hash = main_account.get('account_hash')
    
    if not main_hash:
        return {"status": "error", "reason": "main_account_hash_not_found"}
    
    # Получить enabled клиентов
    slave_accounts = clients_data.get('slave_accounts', [])
    enabled_clients = [c for c in slave_accounts if c.get('enabled', False)]
    
    if not enabled_clients:
        return {"status": "skipped", "reason": "no_enabled_clients"}
    
    # Синхронизировать каждого клиента
    results = []
    for client_data in enabled_clients:
        try:
            client_id = client_data.get('id')
            client_name = client_data.get('name', client_id)
            
            # Получить slave client
            slave_client = get_slave_client(client_id)
            if not slave_client:
                logger.warning(f"[WORKER] Could not get client for {client_id}")
                continue
            
            slave_hash = client_data.get('account_hash')
            if not slave_hash:
                logger.warning(f"[WORKER] No account_hash for {client_id}")
                continue
            
            # Создать synchronizer для одного клиента
            from app.models.copier.synchronizer import PositionSynchronizer
            
            sync_config = client_data.get('settings', {})
            sync_config['client_id'] = client_id
            
            synchronizer = PositionSynchronizer(
                main_client=main_client,
                slave_client=slave_client,
                config=sync_config,
                operating_mode=operating_mode
            )
            
            # Синхронизировать
            result = synchronizer.sync(main_hash, slave_hash)
            results.append({
                'client_id': client_id,
                'client_name': client_name,
                'result': result
            })
            
        except Exception as e:
            import traceback
            logger.error(f"[WORKER] Error syncing {client_data.get('id', 'unknown')}: {e}")
            logger.debug(f"[WORKER] Traceback: {traceback.format_exc()}")
            results.append({
                'client_id': client_data.get('id'),
                'error': str(e)
            })
    
    return {"status": "success", "results": results}


# ═══════════════════════════════════════════════════════════════
# MONITOR MODE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def load_current_delta() -> Dict:
    """Загрузить текущую дельту из файла"""
    return load_json(str(CURRENT_DELTA_FILE), default={})


def save_current_delta(delta_data: Dict):
    """Сохранить текущую дельту в файл"""
    # Убедиться что директория существует
    CURRENT_DELTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(str(CURRENT_DELTA_FILE), delta_data)


def clear_current_delta():
    """Очистить файл текущей дельты"""
    save_current_delta({})


def perform_monitor_sync() -> Dict:
    """
    Выполнить расчёт дельты для Monitor Mode (без выполнения ордеров).
    
    Monitor Live Delta → читает Slave из API (dry_run)
    Monitor Simulation Delta → читает Slave из dry_cache (simulation)
    
    Returns:
        Dict с результатами расчёта дельты для каждого клиента
    """
    from app.core.config_cache import get_clients_from_file
    
    # Определить режим расчёта в зависимости от monitor_sync_mode
    monitor_sync_mode = get_monitor_sync_mode()
    if monitor_sync_mode == 'simulation':
        # Monitor Simulation Delta → читать Slave из dry_cache
        calc_mode = 'simulation'
    else:
        # Monitor Live Delta → читать Slave из API
        calc_mode = 'dry_run'
    
    # Получить main client
    main_client = get_main_client()
    if not main_client:
        return {"status": "error", "reason": "main_client_not_available"}
    
    # Читаем клиентов напрямую из файла
    clients_data = get_clients_from_file()
    
    # Получить main account hash
    main_account = clients_data.get('main_account', {})
    main_hash = main_account.get('account_hash')
    
    if not main_hash:
        return {"status": "error", "reason": "main_account_hash_not_found"}
    
    # Получить enabled клиентов
    slave_accounts = clients_data.get('slave_accounts', [])
    enabled_clients = [c for c in slave_accounts if c.get('enabled', False)]
    
    if not enabled_clients:
        return {"status": "skipped", "reason": "no_enabled_clients"}
    
    # Загрузить текущую дельту для сравнения
    old_delta = load_current_delta()
    new_delta = {}
    delta_changed = False
    
    # Рассчитать дельту для каждого клиента
    results = []
    for client_data in enabled_clients:
        try:
            client_id = client_data.get('id')
            client_name = client_data.get('name', client_id)
            
            # Получить slave client
            slave_client = get_slave_client(client_id)
            if not slave_client:
                logger.warning(f"[WORKER] Could not get client for {client_id}")
                continue
            
            slave_hash = client_data.get('account_hash')
            if not slave_hash:
                logger.warning(f"[WORKER] No account_hash for {client_id}")
                continue
            
            # Получить цены Slave из dry_cache (для SELL ордеров)
            from app.core.cache_manager import get_simulation_cache, get_cached_client
            
            if monitor_sync_mode == 'simulation':
                # Monitor Simulation: Slave из dry_cache
                dry_cache = get_simulation_cache()
                slave_data = dry_cache.get('clients', {}).get(client_id, {})
                slave_positions = slave_data.get('positions', [])
            else:
                # Monitor Live: Slave из API cache
                slave_data = get_cached_client(client_id)
                slave_positions = slave_data.get('positions', []) if slave_data else []
            
            # Создать словарь цен Slave
            slave_prices = {}
            for pos in slave_positions:
                symbol = pos.get('symbol')
                price = pos.get('price', 0)
                if symbol and price:
                    slave_prices[symbol] = price
            
            # Создать synchronizer для расчёта дельты
            from app.models.copier.synchronizer import PositionSynchronizer
            
            sync_config = client_data.get('settings', {})
            sync_config['client_id'] = client_id
            sync_config['is_monitor'] = True
            sync_config['monitor_sync_mode'] = monitor_sync_mode
            
            synchronizer = PositionSynchronizer(
                main_client=main_client,
                slave_client=slave_client,
                config=sync_config,
                operating_mode=calc_mode
            )
            
            # Рассчитать дельту (не выполнять ордера, не записывать в историю)
            result = synchronizer.sync(main_hash, slave_hash, skip_history=True, skip_execution=True)
            
            # Извлечь дельту из результата
            deltas_dict = result.get('deltas', {})
            
            # Цены Main (для BUY ордеров)
            main_prices = result.get('prices', {})
            
            # Преобразовать в формат для current_delta.json
            deltas_list = []
            for symbol, qty in deltas_dict.items():
                if qty != 0:
                    action = "BUY" if qty > 0 else "SELL"
                    
                    # Получить цену из правильного источника
                    if action == "SELL":
                        price = slave_prices.get(symbol, 0)  # SELL: цена из Slave
                    else:
                        price = main_prices.get(symbol, 0)   # BUY: цена из Main
                    
                    value = abs(qty) * price
                    
                    deltas_list.append({
                        "action": action,
                        "symbol": symbol,
                        "qty": abs(qty),
                        "value": round(value, 2)
                    })
            
            # Сохранить в new_delta
            new_delta[client_id] = {
                "client_name": client_name,
                "timestamp": datetime.now().isoformat()[:19],
                "deltas": deltas_list
            }
            
            # Проверить изменилась ли дельта
            old_client_delta = old_delta.get(client_id, {})
            old_deltas = old_client_delta.get('deltas', [])
            if deltas_list != old_deltas:
                delta_changed = True
            
            results.append({
                'client_id': client_id,
                'client_name': client_name,
                'deltas': deltas_list,
                'result': result
            })
            
        except Exception as e:
            import traceback
            logger.error(f"[WORKER] Error calculating delta for {client_data.get('id', 'unknown')}: {e}")
            logger.debug(f"[WORKER] Traceback: {traceback.format_exc()}")
            results.append({
                'client_id': client_data.get('id'),
                'error': str(e)
            })
    
    # Сохранить новую дельту
    save_current_delta(new_delta)
    
    return {
        "status": "success",
        "results": results,
        "delta_changed": delta_changed,
        "new_delta": new_delta
    }


def update_cache() -> Dict:
    """
    Обновить кэш аккаунтов с детальным логированием.
    
    Returns:
        Dict с информацией об обновлении
    """
    from app.core.cache_manager import (
        update_main_account_for_worker,
        update_clients_for_worker,
        get_cache_file_lock,
        save_json,
        set_cache_updated
    )
    from app.core.paths import DATA_DIR
    
    result = {"main_updated": False, "clients_updated": 0, "clients_total": 0}
    
    try:
        # Обновить Main
        main_data = update_main_account_for_worker()
        if main_data:
            result["main_updated"] = True
            logger.info("[WORKER] Main account updated")
        else:
            logger.warning("[WORKER] Main account update failed")
        
        # Обновить Clients
        clients_data = update_clients_for_worker()
        if clients_data:
            result["clients_updated"] = len(clients_data)
            result["clients_total"] = len(clients_data)
            # Логи по именам клиентов
            for client_id, client_info in clients_data.items():
                client_name = client_info.get('client_name', client_id)
                logger.info(f"[WORKER] {client_name} account updated")
        
        # Сохранить кэш если оба успешно
        if main_data and clients_data is not None:
            cache_file = DATA_DIR / "account_cache.json"
            cache_lock = get_cache_file_lock()
            with cache_lock:
                cache = {
                    'main_account': main_data,
                    'clients': clients_data,
                    'last_updated': datetime.now().isoformat()
                }
                save_json(str(cache_file), cache)
            set_cache_updated(True)
        
    except Exception as e:
        logger.error(f"[WORKER] Cache update error: {e}")
    
    return result


def _parse_history_timestamp(timestamp_str: str) -> datetime:
    """Парсить timestamp из истории для сравнения"""
    try:
        if 'T' in timestamp_str:
            # ISO формат: 2026-01-22T09:51:54.653783
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        else:
            return datetime.min
    except Exception:
        return datetime.min


# ═══════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════


def send_telegram_message(message: str):
    """Отправить Telegram сообщение"""
    settings = load_json(GENERAL_SETTINGS_FILE, default={})
    notifications = settings.get("notifications", {})
    
    if not notifications.get("telegram_enabled", False):
        return
    
    bot_token = notifications.get("telegram_bot_token", "")
    chat_id = notifications.get("telegram_chat_id", "")
    
    if not bot_token or not chat_id:
        return
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logger.warning(f"[WORKER] Telegram error: {e}")

# ═══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════


class SyncWorker:
    """Worker для автоматической синхронизации"""
    
    def __init__(self):
        self.running = False
        self.last_heartbeat = datetime.now()
        self.last_sync = None
        # Флаги для отслеживания состояния биржи
        self.market_open_iteration = 0
        self.market_closed_iteration = 0
        
    def start(self):
        """Запустить worker"""
        # Проверить и сбросить "осиротевший" статус (если старый PID мёртв)
        cleanup_stale_status()
        
        # Проверить — не запущен ли уже другой Worker
        status = load_worker_status()
        old_pid = status.get("pid")
        current_pid = os.getpid()
        
        if old_pid and old_pid != current_pid and is_process_alive(old_pid):
            logger.error(f"[WORKER] Worker is already running (PID {old_pid})")
            sys.exit(42)  # Специальный код — "already running"
        
        # Записать свой PID сразу
        status["pid"] = current_pid
        save_worker_status(status)
        
        logger.info("[WORKER] ════════════════════════════════════════")
        logger.info("[WORKER] ▶️  Starting Sync Worker")
        logger.info(f"[WORKER] PID: {current_pid}")
        logger.info("[WORKER] ════════════════════════════════════════")
        
        # Установить обработчик сигналов
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.running = True
        
        while self.running:
            try:
                self._main_loop()
            except Exception as e:
                logger.error(f"[WORKER] Main loop error: {e}")
                time.sleep(CHECK_COMMAND_INTERVAL)
        
        # Cleanup
        allow_sleep()
        set_worker_running(False)
        logger.info("[WORKER] Stopped")
    
    def _signal_handler(self, signum, _frame):
        """Обработчик сигналов (SIGINT, SIGTERM)"""
        logger.info(f"[WORKER] Received signal {signum}, stopping...")
        self.running = False
    
    def _main_loop(self):
        """Основной цикл"""
        # Читаем статус
        status = load_worker_status()
        command = status.get("command", "stop")
        
        # Проверяем жив ли GUI
        if not is_gui_alive():
            # GUI мёртв — если работали, остановиться
            if status.get("running", False):
                allow_sleep()
                set_worker_running(False)
                reset_gui_sync_timer()
                logger.info("[WORKER] GUI not running, stopping Auto Sync")
            time.sleep(CHECK_COMMAND_INTERVAL)
            return
        
        # Обновляем heartbeat
        if (datetime.now() - self.last_heartbeat).seconds >= HEARTBEAT_INTERVAL:
            update_heartbeat(status)
            self.last_heartbeat = datetime.now()
        
        # Обработка команд
        if command == "stop":
            if status.get("running", False):
                # Было running → остановка
                allow_sleep()
                set_worker_running(False)
                reset_gui_sync_timer()  # Сбросить таймер GUI
                clear_current_delta()   # Очистить текущую дельту
                clear_client_cache()    # Очистить кэш клиентов (для свежих токенов при restart)
                # Сбросить флаги состояния биржи
                self.market_open_iteration = 0
                self.market_closed_iteration = 0
                
                # Telegram сообщение об остановке
                import pytz
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.now(et_tz)
                time_str = now_et.strftime("%A, %d.%m.%Y, %H:%M ET")
                
                operating_mode = get_operating_mode()
                monitor_sync_mode = get_monitor_sync_mode()
                
                if operating_mode == 'monitor' and monitor_sync_mode == 'simulation':
                    send_telegram_message(f"🔍🔶 Monitor Simulation Delta\n⏹️ Stopped\n⏰ {time_str}")
                elif operating_mode == 'monitor' and monitor_sync_mode == 'live':
                    send_telegram_message(f"🔍🔴 Monitor Live Delta\n⏹️ Stopped\n⏰ {time_str}")
                elif operating_mode == 'simulation':
                    send_telegram_message(f"🔶 Simulation: Auto Sync\n⏹️ Stopped\n⏰ {time_str}")
                elif operating_mode == 'live':
                    send_telegram_message(f"🔴 Live Mode\n⏹️ Stopped\n⏰ {time_str}")
                else:
                    send_telegram_message("🛑 Auto Sync Stopped")
                
                logger.info("[WORKER] Auto Sync stopped by command")
            time.sleep(CHECK_COMMAND_INTERVAL)
            return
        
        if command == "apply":
            # Команда Apply: выполнить ордера из текущей дельты
            logger.info("[WORKER] Apply command received")
            self._do_apply(status)
            # Сбросить команду на "start" чтобы продолжить мониторинг
            status["command"] = "start"
            save_worker_status(status)
            return
        
        if command == "start":
            if not status.get("running", False):
                # Не было running → "чистый старт"
                # Сбросить кэш клиентов для получения свежих токенов
                clear_client_cache()
                
                # Сбросить last_sync чтобы sync выполнился сразу
                self.last_sync = None
                
                # Сбросить флаги состояния биржи (для нового цикла)
                self.market_open_iteration = 0
                self.market_closed_iteration = 0
                
                prevent_sleep()
                set_worker_running(True)
                
                # Перезагрузить status чтобы _do_sync_iteration видел running=True
                status = load_worker_status()
                
                # Telegram сообщение о старте
                import pytz
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.now(et_tz)
                time_str = now_et.strftime("%A, %d.%m.%Y, %H:%M ET")
                
                operating_mode = get_operating_mode()
                monitor_sync_mode = get_monitor_sync_mode()
                
                if operating_mode == 'monitor' and monitor_sync_mode == 'simulation':
                    send_telegram_message(f"🔍🔶 Monitor Simulation Delta\n▶️ Started\n⏰ {time_str}")
                elif operating_mode == 'monitor' and monitor_sync_mode == 'live':
                    send_telegram_message(f"🔍🔴 Monitor Live Delta\n▶️ Started\n⏰ {time_str}")
                elif operating_mode == 'simulation':
                    send_telegram_message(f"🔶 Simulation: Auto Sync\n▶️ Started\n⏰ {time_str}")
                elif operating_mode == 'live':
                    send_telegram_message(f"🔴 Live Mode\n▶️ Started\n⏰ {time_str}")
                else:
                    send_telegram_message("▶️ Auto Sync Started")
                
                logger.info("[WORKER] Auto Sync started by command")
                
                # Таймер GUI обновится после первого sync (update_gui_sync_status)
            
            # "Пинг" для Modern Standby на каждой итерации (каждые ~5 сек)
            ping_prevent_sleep()
            
            # Выполняем синхронизацию
            self._do_sync_iteration(status)
    
    def _do_sync_iteration(self, status: Dict):
        """Одна итерация синхронизации"""
        operating_mode = get_operating_mode()
        monitor_sync_mode = get_monitor_sync_mode()
        interval = get_sync_interval_seconds()
        
        # Проверяем нужна ли синхронизация
        if self.last_sync:
            elapsed = (datetime.now() - self.last_sync).seconds
            if elapsed < interval:
                time.sleep(CHECK_COMMAND_INTERVAL)
                return
        
        # ═══════════════════════════════════════════════════════════════
        # 1. Старт итерации
        # ═══════════════════════════════════════════════════════════════
        et_time = get_et_time_str()
        logger.info("[WORKER] ════════════════════════════════════════")
        
        # Определить иконку режима
        if operating_mode == 'monitor' and monitor_sync_mode == 'simulation':
            logger.info(f"[WORKER] 🔍 🔶 Sync iteration started ({et_time})")
        elif operating_mode == 'monitor' and monitor_sync_mode == 'live':
            logger.info(f"[WORKER] 🔍 🔴 Sync iteration started ({et_time})")
        elif operating_mode == 'simulation':
            logger.info(f"[WORKER] 🔶 Sync iteration started ({et_time})")
        elif operating_mode == 'live':
            logger.info(f"[WORKER] 🔴 Sync iteration started ({et_time})")
        else:
            logger.info(f"[WORKER] ▶️ Sync iteration started ({et_time})")
        
        logger.info("[WORKER] ════════════════════════════════════════")
        
        # ═══════════════════════════════════════════════════════════════
        # 2. Обновляем кэш (логи внутри update_cache)
        # ═══════════════════════════════════════════════════════════════
        update_cache()
        
        # ═══════════════════════════════════════════════════════════════
        # 3. Проверяем рынок
        # ═══════════════════════════════════════════════════════════════
        is_open, reason = is_market_open()
        
        # ═══════════════════════════════════════════════════════════════
        # 4. Monitor Simulation Delta — специальная логика с флагами
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'monitor' and monitor_sync_mode == 'simulation':
            from app.core.cache_manager import copy_cache_to_dry, copy_main_account_to_dry
            
            # 4.3/4.4: Копирование cache → dry_cache
            if self.market_open_iteration == 0 and self.market_closed_iteration == 0:
                # Первый запуск: полная копия
                copy_cache_to_dry()
                logger.info("[WORKER] Full cache copied to dry_cache (first run)")
            else:
                # Последующие итерации: только main_account
                copy_main_account_to_dry()
            
            # 4.5: Проверка биржи
            if is_open:
                # Биржа открыта
                # 4.6: Если биржа только что открылась
                if self.market_open_iteration == 0 and self.market_closed_iteration > 0:
                    # 4.6.1: Toast
                    from app.core.sync_common import get_notification_settings
                    from app.core.notification_service import get_notification_service
                    notif_settings = get_notification_settings()
                    if notif_settings.get('toast_on_success', False):
                        notif = get_notification_service()
                        notif.info("The market is open. Sync is enabled.")
                    # 4.6.2: Telegram
                    send_telegram_message("🔔 Market Opened\nThe market is open. Sync is enabled.")
                    # 4.6.3: Сброс флага
                    self.market_closed_iteration = 0
                
                # 4.7: Инкремент флага
                if self.market_open_iteration == 0 and self.market_closed_iteration == 0:
                    # 4.7.1, 4.7.2: Первая итерация при открытой бирже
                    self.market_open_iteration += 1
                    logger.info("[WORKER] The market is open, synchronization is enabled.")
                else:
                    # Последующие итерации
                    self.market_open_iteration += 1
                
                # 4.7.3-4.7.6: Синхронизация (расчёт дельты)
                result = perform_monitor_sync()
                
                self.last_sync = datetime.now()
                status["last_sync"] = self.last_sync.isoformat()
                status["last_sync_result"] = result.get("status", "unknown")
                save_worker_status(status)
                update_gui_sync_status()
                
                # Логи результата
                delta_changed = result.get("delta_changed", False)
                results_list = result.get("results", [])
                
                has_delta = False
                for client_result in results_list:
                    deltas = client_result.get('deltas', [])
                    client_name = client_result.get('client_name', 'Unknown')
                    
                    if deltas:
                        has_delta = True
                        logger.info(f"[WORKER] {client_name}: Positions are not synchronized, delta is:")
                        for d in deltas:
                            logger.info(f"[WORKER]    {d['action']} / {d['symbol']} / {d['qty']} / ${d['value']:,.2f}")
                    else:
                        logger.info(f"[WORKER] ✅ {client_name}: Positions are synchronized, no delta")
                
                # 4.7.6: Telegram при изменении дельты
                if delta_changed and has_delta:
                    import pytz
                    et_tz = pytz.timezone('US/Eastern')
                    now_et = datetime.now(et_tz)
                    time_str = now_et.strftime("%A, %d.%m.%Y, %H:%M ET")
                    
                    msg_lines = ["🔍🔶 Monitor Simulation Delta"]
                    for client_result in results_list:
                        deltas = client_result.get('deltas', [])
                        if deltas:
                            for d in deltas:
                                msg_lines.append(f"{d['action']} / {d['symbol']} / {d['qty']} / ${d['value']:,.2f}")
                    msg_lines.append(f"⏰ {time_str}")
                    send_telegram_message("\n".join(msg_lines))
                
                return
            
            else:
                # Биржа закрыта
                # 4.9: Если биржа только что закрылась
                if self.market_open_iteration > 0 and self.market_closed_iteration == 0:
                    # 4.9.1: Toast
                    from app.core.sync_common import get_notification_settings
                    from app.core.notification_service import get_notification_service
                    notif_settings = get_notification_settings()
                    if notif_settings.get('toast_on_success', False):
                        notif = get_notification_service()
                        notif.info("Market closed. Sync is suspended.")
                    # 4.9.2: Telegram
                    send_telegram_message("🔔 Market Closed\nMarket closed. Sync is suspended.")
                    # 4.9.3: Сброс флага
                    self.market_open_iteration = 0
                
                # 4.10: Инкремент флага закрытия
                self.market_closed_iteration += 1
                logger.info("[WORKER] The market is closed, synchronization is suspended.")
                
                self.last_sync = datetime.now()
                status["last_sync"] = self.last_sync.isoformat()
                status["last_sync_result"] = "market_closed"
                save_worker_status(status)
                update_gui_sync_status()
                return
        
        # ═══════════════════════════════════════════════════════════════
        # 4.5. Simulation Mode — специальная логика с флагами
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'simulation':
            from app.core.cache_manager import copy_cache_to_dry, copy_main_account_to_dry
            
            # 4.3/4.4: Копирование cache → dry_cache
            if self.market_open_iteration == 0 and self.market_closed_iteration == 0:
                # Первый запуск: полная копия
                copy_cache_to_dry()
                logger.info("[WORKER] Full cache copied to dry_cache (first run)")
            else:
                # Последующие итерации: только main_account
                copy_main_account_to_dry()
            
            # 4.5: Проверка биржи
            if is_open:
                # Биржа открыта
                # 4.6: Если биржа только что открылась
                if self.market_open_iteration == 0 and self.market_closed_iteration > 0:
                    # 4.6.1: Toast
                    from app.core.sync_common import get_notification_settings
                    from app.core.notification_service import get_notification_service
                    notif_settings = get_notification_settings()
                    if notif_settings.get('toast_on_success', False):
                        notif = get_notification_service()
                        notif.info("The market is open. Sync is enabled.")
                    # 4.6.2: Telegram
                    send_telegram_message("🔔 Market Opened\nThe market is open. Sync is enabled.")
                    # 4.6.3: Сброс флага
                    self.market_closed_iteration = 0
                
                # 4.7: Инкремент флага
                if self.market_open_iteration == 0 and self.market_closed_iteration == 0:
                    # 4.7.1, 4.7.2: Первая итерация при открытой бирже
                    self.market_open_iteration += 1
                    logger.info("[WORKER] The market is open, synchronization is enabled.")
                else:
                    # Последующие итерации
                    self.market_open_iteration += 1
                
                # 4.7.3-4.7.4: Синхронизация (автоматическое выполнение)
                result = perform_sync()
                
                self.last_sync = datetime.now()
                status["last_sync"] = self.last_sync.isoformat()
                status["last_sync_result"] = result.get("status", "unknown")
                save_worker_status(status)
                update_gui_sync_status()
                
                # Логи результата
                results_list = result.get("results", [])
                total_orders = 0
                has_delta = False
                
                for client_result in results_list:
                    r = client_result.get("result", {})
                    client_name = client_result.get('client_name', 'Unknown')
                    summary = r.get("summary", {})
                    orders_placed = summary.get("orders_placed", 0)
                    total_orders += orders_placed
                    
                    if orders_placed > 0:
                        has_delta = True
                        # 4.7.4.1: Лог с деталями
                        logger.info(f"[WORKER] {client_name}: Positions are synchronized, delta is reset:")
                        orders = r.get('results', [])
                        for order in orders:
                            action = order.get('action', '?')
                            symbol = order.get('symbol', '?')
                            qty = order.get('quantity', 0)
                            price = order.get('price', 0)
                            value = qty * price
                            logger.info(f"[WORKER]    {action} / {symbol} / {qty} / ${value:,.2f}")
                    else:
                        # 4.7.3.1: Нет дельты
                        logger.info(f"[WORKER] {client_name}: Positions are synchronized.")
                
                # 4.7.4.4, 4.7.4.5: Telegram при синхронизации
                if has_delta:
                    import pytz
                    et_tz = pytz.timezone('US/Eastern')
                    now_et = datetime.now(et_tz)
                    time_str = now_et.strftime("%A, %d.%m.%Y, %H:%M ET")
                    
                    # notify_sync_status
                    send_telegram_message(f"🔶 Simulation: Auto Sync\n✅ Positions Synced\n⏰ {time_str}")
                    
                    # notify_positions_synced (детали)
                    details_lines = [f"📊 Orders: {total_orders}"]
                    for client_result in results_list:
                        r = client_result.get('result', {})
                        client_name = client_result.get('client_name', 'Unknown')
                        orders = r.get('results', [])
                        if orders:
                            details_lines.append(f"\n{client_name}:")
                            for order in orders:
                                action = order.get('action', '?')
                                symbol = order.get('symbol', '?')
                                qty = order.get('quantity', 0)
                                price = order.get('price', 0)
                                details_lines.append(f"  {action} {symbol} x{qty} @ ${price:.2f}")
                    send_telegram_message("\n".join(details_lines))
                
                return
            
            else:
                # Биржа закрыта
                # 4.9: Если биржа только что закрылась
                if self.market_open_iteration > 0 and self.market_closed_iteration == 0:
                    # 4.9.1: Toast
                    from app.core.sync_common import get_notification_settings
                    from app.core.notification_service import get_notification_service
                    notif_settings = get_notification_settings()
                    if notif_settings.get('toast_on_success', False):
                        notif = get_notification_service()
                        notif.info("Market closed. Sync is suspended.")
                    # 4.9.2: Telegram
                    send_telegram_message("🔔 Market Closed\nMarket closed. Sync is suspended.")
                    # 4.9.3: Сброс флага
                    self.market_open_iteration = 0
                
                # 4.10: Инкремент флага закрытия
                self.market_closed_iteration += 1
                logger.info("[WORKER] The market is closed, synchronization is suspended.")
                
                self.last_sync = datetime.now()
                status["last_sync"] = self.last_sync.isoformat()
                status["last_sync_result"] = "market_closed"
                save_worker_status(status)
                update_gui_sync_status()
                return
        
        # ═══════════════════════════════════════════════════════════════
        # 5. Остальные режимы — старая логика
        # ═══════════════════════════════════════════════════════════════
        
        # Синхронизация только если рынок открыт (для LIVE и Monitor Live)
        if operating_mode == 'live' and not is_open:
            logger.info("[WORKER] Market closed, Sync skipped")
            self.last_sync = datetime.now()
            status["last_sync"] = self.last_sync.isoformat()
            status["last_sync_result"] = "market_closed"
            save_worker_status(status)
            update_gui_sync_status()
            return
        
        # Monitor Live Delta - пропустить если рынок закрыт
        if operating_mode == 'monitor' and monitor_sync_mode == 'live' and not is_open:
            logger.info("[WORKER] Market closed, Monitor skipped")
            self.last_sync = datetime.now()
            status["last_sync"] = self.last_sync.isoformat()
            status["last_sync_result"] = "market_closed"
            save_worker_status(status)
            update_gui_sync_status()
            return
        
        # ═══════════════════════════════════════════════════════════════
        # 6. Выполняем синхронизацию (для остальных режимов)
        # ═══════════════════════════════════════════════════════════════
        
        if operating_mode == 'monitor':
            # MONITOR MODE (Live): только рассчитать дельту, не выполнять ордера
            result = perform_monitor_sync()
            
            self.last_sync = datetime.now()
            status["last_sync"] = self.last_sync.isoformat()
            status["last_sync_result"] = result.get("status", "unknown")
            save_worker_status(status)
            update_gui_sync_status()
            
            # Логи результата Monitor Mode
            delta_changed = result.get("delta_changed", False)
            results_list = result.get("results", [])
            
            has_delta = False
            for client_result in results_list:
                deltas = client_result.get('deltas', [])
                client_name = client_result.get('client_name', 'Unknown')
                
                if deltas:
                    has_delta = True
                    logger.info(f"[WORKER] 🔍 Delta for {client_name}:")
                    for d in deltas:
                        logger.info(f"[WORKER]    {d['action']} / {d['symbol']} / {d['qty']} / ${d['value']:,.2f}")
                else:
                    logger.info(f"[WORKER] ✅ {client_name}: Positions synchronized, no delta")
            
            # Отправить Telegram при изменении дельты
            if delta_changed and has_delta:
                mode_icon = "🔍🔴" if monitor_sync_mode == 'live' else "🔍🔶"
                msg_lines = [f"{mode_icon} Delta Changed:"]
                for client_result in results_list:
                    deltas = client_result.get('deltas', [])
                    if deltas:
                        for d in deltas:
                            msg_lines.append(f"{d['action']} / {d['symbol']} / {d['qty']} / ${d['value']:,.2f}")
                send_telegram_message("\n".join(msg_lines))
            
            return
        
        # LIVE / SIMULATION MODE: выполнить синхронизацию
        result = perform_sync()
        
        self.last_sync = datetime.now()
        status["last_sync"] = self.last_sync.isoformat()
        status["last_sync_result"] = result.get("status", "unknown")
        save_worker_status(status)
        
        # Обновить GUI таймер
        update_gui_sync_status()
        
        # ═══════════════════════════════════════════════════════════════
        # 5. Логи результата
        # ═══════════════════════════════════════════════════════════════
        results_list = result.get("results", [])
        total_orders = 0
        
        for client_result in results_list:
            r = client_result.get("result", {})
            summary = r.get("summary", {})
            orders_placed = summary.get("orders_placed", 0)
            total_orders += orders_placed
        
        if total_orders == 0:
            logger.info("[WORKER] ☑️ No synchronization required")
        else:
            logger.info(f"[WORKER] 🔛 Positions synchronized ({total_orders} orders)")
    
    def _do_apply(self, _status: Dict):
        """
        Выполнить Apply: ордера из текущей дельты.
        
        Monitor Live Delta → реальные ордера
        Monitor Simulation Delta → виртуальные ордера
        """
        monitor_sync_mode = get_monitor_sync_mode()
        mode_icon = "🔍🔴" if monitor_sync_mode == 'live' else "🔍🔶"
        
        # Проверить есть ли дельта
        delta_data = load_current_delta()
        if not delta_data:
            logger.info(f"[WORKER] {mode_icon} Apply: No delta data")
            return
        
        # Проверить есть ли ненулевая дельта
        has_delta = False
        for client_id, client_data in delta_data.items():
            if client_data.get('deltas', []):
                has_delta = True
                break
        
        if not has_delta:
            logger.info(f"[WORKER] {mode_icon} Apply: Positions are synchronized, no delta")
            return
        
        logger.info(f"[WORKER] {mode_icon} Apply: Executing orders...")
        
        # Выполнить синхронизацию
        # perform_sync() использует operating_mode из настроек
        # Для Monitor режима нужно временно установить режим
        if monitor_sync_mode == 'live':
            # Monitor Live Delta → реальные ордера (как live mode)
            result = self._perform_apply_live()
        else:
            # Monitor Simulation Delta → виртуальные ордера
            result = self._perform_apply_simulation()
        
        # Проверить результат
        if result.get('status') == 'success':
            results_list = result.get('results', [])
            total_orders = 0
            
            for client_result in results_list:
                r = client_result.get('result', {})
                summary = r.get('summary', {})
                orders_placed = summary.get('orders_placed', 0)
                total_orders += orders_placed
            
            # Очистить текущую дельту (позиции синхронизированы)
            clear_current_delta()
            
            logger.info(f"[WORKER] {mode_icon} Apply: ✅ Positions synced ({total_orders} orders)")
            
            # Telegram сообщение 1: notify_sync_status
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            time_str = now_et.strftime("%A, %d.%m.%Y, %H:%M ET")
            
            mode_name = "Monitor Live Delta" if monitor_sync_mode == 'live' else "Monitor Simulation Delta"
            send_telegram_message(f"{mode_icon} {mode_name}\n✅ Positions Synced\n⏰ {time_str}")
            
            # Telegram сообщение 2: notify_positions_synced (детали)
            if total_orders > 0:
                details_lines = [f"📊 Orders: {total_orders}"]
                for client_result in results_list:
                    r = client_result.get('result', {})
                    client_name = client_result.get('client_name', 'Unknown')
                    orders = r.get('results', [])
                    if orders:
                        details_lines.append(f"\n{client_name}:")
                        for order in orders:
                            action = order.get('action', '?')
                            symbol = order.get('symbol', '?')
                            qty = order.get('quantity', 0)
                            price = order.get('price', 0)
                            details_lines.append(f"  {action} {symbol} x{qty} @ ${price:.2f}")
                send_telegram_message("\n".join(details_lines))
        else:
            reason = result.get('reason', 'Unknown error')
            logger.error(f"[WORKER] {mode_icon} Apply: ❌ Failed - {reason}")
            send_telegram_message(f"{mode_icon} Apply\n❌ Failed - {reason}")
    
    @staticmethod
    def _perform_apply_live() -> Dict:
        """Выполнить Apply в режиме Live (реальные ордера)"""
        from app.core.config_cache import get_clients_from_file
        
        main_client = get_main_client()
        if not main_client:
            return {"status": "error", "reason": "main_client_not_available"}
        
        clients_data = get_clients_from_file()
        main_account = clients_data.get('main_account', {})
        main_hash = main_account.get('account_hash')
        
        if not main_hash:
            return {"status": "error", "reason": "main_account_hash_not_found"}
        
        slave_accounts = clients_data.get('slave_accounts', [])
        enabled_clients = [c for c in slave_accounts if c.get('enabled', False)]
        
        if not enabled_clients:
            return {"status": "skipped", "reason": "no_enabled_clients"}
        
        results = []
        for client_data in enabled_clients:
            try:
                client_id = client_data.get('id')
                client_name = client_data.get('name', client_id)
                
                slave_client = get_slave_client(client_id)
                if not slave_client:
                    continue
                
                slave_hash = client_data.get('account_hash')
                if not slave_hash:
                    continue
                
                # Использовать LiveSync для реальных ордеров
                from app.modes.live.sync import LiveSync
                
                sync_config = client_data.get('settings', {})
                sync_config['client_id'] = client_id
                
                live_sync = LiveSync(
                    main_client=main_client,
                    slave_client=slave_client,
                    config=sync_config
                )
                
                result = live_sync.sync(main_hash, slave_hash)
                results.append({
                    'client_id': client_id,
                    'client_name': client_name,
                    'result': result
                })
                
            except Exception as e:
                logger.error(f"[WORKER] Apply Live error for {client_data.get('id')}: {e}")
                results.append({
                    'client_id': client_data.get('id'),
                    'error': str(e)
                })
        
        return {"status": "success", "results": results}
    
    @staticmethod
    def _perform_apply_simulation() -> Dict:
        """
        Выполнить Apply в режиме Monitor Simulation Delta.
        
        НЕ пересчитывает дельту — берёт готовую из current_delta.json.
        Обновляет dry_cache и записывает историю.
        """
        from app.core.config_cache import get_clients_from_file
        from app.core.cache_manager import (
            get_simulation_cache, 
            update_simulation_cache,
            copy_main_account_to_dry,
            CACHE_FILE
        )
        from app.core.paths import get_client_history_dry_file
        from app.models.copier.calculator import PositionCalculator
        
        # 1. Загрузить current_delta.json
        delta_data = load_current_delta()
        if not delta_data:
            return {"status": "skipped", "reason": "no_delta_data"}
        
        # 2. Загрузить кэши
        dry_cache = get_simulation_cache()
        
        # Загрузить реальный кэш для Main позиций (для цен BUY)
        real_cache = load_json(str(CACHE_FILE), default={})
        main_data = real_cache.get('main_account', {})
        main_positions = main_data.get('positions', [])
        main_equity = main_data.get('balances', {}).get('liquidation_value', 0)
        
        # Создать словарь цен из Main позиций
        main_prices = {}
        for pos in main_positions:
            symbol = pos.get('symbol')
            price = pos.get('price', 0)
            if symbol and price:
                main_prices[symbol] = price
        
        # 3. Загрузить настройки клиентов
        clients_data = get_clients_from_file()
        slave_accounts = clients_data.get('slave_accounts', [])
        clients_by_id = {c.get('id'): c for c in slave_accounts}
        
        calculator = PositionCalculator()
        results = []
        
        # 4. Обработать каждого клиента с дельтой
        for client_id, client_delta in delta_data.items():
            try:
                client_name = client_delta.get('client_name', client_id)
                deltas_list = client_delta.get('deltas', [])
                
                if not deltas_list:
                    continue
                
                # Получить данные клиента из dry_cache
                client_dry_data = dry_cache.get('clients', {}).get(client_id, {})
                slave_positions = client_dry_data.get('positions', [])
                slave_equity = client_dry_data.get('balances', {}).get('liquidation_value', 0)
                
                # Создать словарь цен из Slave позиций (для SELL)
                slave_prices = {}
                for pos in slave_positions:
                    symbol = pos.get('symbol')
                    price = pos.get('price', 0)
                    if symbol and price:
                        slave_prices[symbol] = price
                
                # Получить настройки клиента для scale
                client_config = clients_by_id.get(client_id, {})
                client_settings = client_config.get('settings', {})
                
                # Рассчитать scale
                scale = calculator.calculate_scale(
                    main_equity,
                    slave_equity,
                    method=client_settings.get('scale_method', 'DYNAMIC_RATIO'),
                    fixed_amount=client_settings.get('fixed_amount'),
                    slave_equity_nomin=client_settings.get('slave_equity_nomin'),
                    usage_percent=client_settings.get('usage_percent', 100)
                )
                
                # Сформировать deltas dict и results для истории
                now = datetime.now()
                timestamp_str = now.strftime("%H%M%S")
                deltas_dict = {}
                order_results = []
                
                for delta_item in deltas_list:
                    action = delta_item.get('action')
                    symbol = delta_item.get('symbol')
                    qty = delta_item.get('qty', 0)
                    
                    # Определить знак для deltas_dict
                    if action == 'BUY':
                        deltas_dict[symbol] = qty
                    else:  # SELL
                        deltas_dict[symbol] = -qty
                    
                    # Получить цену
                    if action == 'SELL':
                        price = slave_prices.get(symbol, 0)
                    else:  # BUY
                        price = main_prices.get(symbol, 0)
                    
                    order_results.append({
                        "symbol": symbol,
                        "action": action,
                        "quantity": qty,
                        "price": price,
                        "status": "SIMULATED",
                        "order_id": f"SIM-{timestamp_str}-{symbol}",
                        "timestamp": now.isoformat()
                    })
                
                # Сформировать запись истории
                history_entry = {
                    "timestamp": now.isoformat(),
                    "status": "SIMULATED",
                    "operating_mode": "monitor_simulation",
                    "scale": scale,
                    "main_equity": main_equity,
                    "slave_equity": slave_equity,
                    "deltas": deltas_dict,
                    "valid_deltas": deltas_dict,
                    "results": order_results,
                    "errors": [],
                    "summary": {
                        "total_deltas": len(deltas_list),
                        "orders_placed": len(order_results),
                        "orders_success": len(order_results),
                        "orders_failed": 0
                    }
                }
                
                # Записать в history_dry
                history_file = get_client_history_dry_file(client_id)
                history = load_json(str(history_file), default=[])
                history.append(history_entry)
                
                # Удалить записи старше 6 месяцев
                from datetime import timedelta
                six_months_ago = datetime.now() - timedelta(days=180)
                history = [
                    entry for entry in history
                    if _parse_history_timestamp(entry.get('timestamp', '')) > six_months_ago
                ]
                
                save_json(str(history_file), history)
                logger.debug(f"[APPLY] History saved to {history_file}")
                
                # Обновить позиции клиента в dry_cache
                # Позиции = как у Main, но количество × scale
                new_positions = []
                new_positions_value = 0
                
                for main_pos in main_positions:
                    symbol = main_pos.get('symbol')
                    main_qty = main_pos.get('quantity', 0)
                    price = main_pos.get('price', 0)
                    avg_price = main_pos.get('average_price', price)
                    
                    # Рассчитать количество для slave
                    target_qty = calculator.calculate_target_quantity(
                        main_qty, 
                        scale,
                        rounding_method=client_settings.get('rounding_method', 'ROUND_DOWN')
                    )
                    
                    if target_qty > 0:
                        market_value = target_qty * price
                        new_positions_value += market_value
                        
                        new_positions.append({
                            "symbol": symbol,
                            "quantity": target_qty,
                            "price": price,
                            "average_price": avg_price,
                            "market_value": market_value,
                            "unrealized_pl": 0
                        })
                
                # Обновить балансы клиента
                new_cash_balance = slave_equity - new_positions_value
                
                dry_cache['clients'][client_id] = {
                    "client_id": client_id,
                    "client_name": client_name,
                    "account_hash": client_dry_data.get('account_hash', ''),
                    "total_value": slave_equity,
                    "positions_value": new_positions_value,
                    "balances": {
                        "liquidation_value": slave_equity,
                        "positions_value": new_positions_value,
                        "cash_balance": new_cash_balance,
                        "buying_power": 0,
                        "available_funds": new_cash_balance
                    },
                    "positions": new_positions,
                    "positions_count": len(new_positions),
                    "total_pl": 0
                }
                
                results.append({
                    'client_id': client_id,
                    'client_name': client_name,
                    'result': history_entry
                })
                
                logger.info(f"[APPLY] {client_name}: {len(order_results)} orders applied")
                
            except Exception as e:
                import traceback
                logger.error(f"[APPLY] Error for {client_id}: {e}")
                logger.debug(f"[APPLY] Traceback: {traceback.format_exc()}")
                results.append({
                    'client_id': client_id,
                    'error': str(e)
                })
        
        # 5. Сохранить обновлённый dry_cache
        update_simulation_cache(dry_cache)
        
        # 6. Скопировать свежий main_account в dry_cache
        copy_main_account_to_dry()
        
        return {"status": "success", "results": results}

# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════


if __name__ == "__main__":
    # Настройка логера
    setup_logger(level="INFO", console=True)
    
    # Перехват stdout для сообщений schwab библиотеки
    class StdoutInterceptor:
        """Перехватывает print() и направляет в logger"""
        def __init__(self, original_stdout):
            self.original = original_stdout
            self.last_schwab_message = None
            
        def write(self, message):
            msg = message.strip()
            if msg:
                msg_lower = msg.lower()
                # Сообщения schwab → WARNING в лог (без дубликатов)
                is_schwab_message = (
                    "refresh token will expire" in msg_lower or
                    "refresh_token" in msg_lower or
                    "could not get new access token" in msg_lower or
                    "error_description" in msg_lower or
                    '"error":' in msg_lower
                )
                
                if is_schwab_message:
                    if msg != self.last_schwab_message:
                        logger.warning(f"[SCHWAB] {msg}")
                        self.last_schwab_message = msg
                    # Не выводить в консоль
                else:
                    # Остальные print → оригинальный stdout
                    self.original.write(message)
            elif message == '\n':
                # Пропускаем пустые строки от schwab
                pass
            else:
                self.original.write(message)
                
        def flush(self):
            self.original.flush()
    
    sys.stdout = StdoutInterceptor(sys.stdout)
    
    # Запуск worker
    worker = SyncWorker()
    worker.start()
