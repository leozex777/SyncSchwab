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
    
    Returns:
        (is_open: bool, reason: str)
    """
    import pytz
    from datetime import time as dt_time
    
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    
    # Выходные
    if now.weekday() >= 5:
        return False, "Weekend"
    
    # Время
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
        self.market_was_open = None
        
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
        logger.info("[WORKER] Starting Sync Worker")
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
                send_telegram_message("🛑 Auto Sync Stopped")
                logger.info("[WORKER] Auto Sync stopped by command")
            time.sleep(CHECK_COMMAND_INTERVAL)
            return
        
        if command == "start":
            if not status.get("running", False):
                # Не было running → "чистый старт"
                # Сбросить кэш клиентов для получения свежих токенов
                clear_client_cache()
                
                # Сбросить last_sync чтобы sync выполнился сразу
                self.last_sync = None
                
                prevent_sleep()
                set_worker_running(True)
                
                # Перезагрузить status чтобы _do_sync_iteration видел running=True
                status = load_worker_status()
                
                send_telegram_message("▶️ Auto Sync Started (Worker)")
                logger.info("[WORKER] Auto Sync started by command")
                
                # Таймер GUI обновится после первого sync (update_gui_sync_status)
            
            # "Пинг" для Modern Standby на каждой итерации (каждые ~5 сек)
            ping_prevent_sleep()
            
            # Выполняем синхронизацию
            self._do_sync_iteration(status)
    
    def _do_sync_iteration(self, status: Dict):
        """Одна итерация синхронизации"""
        operating_mode = get_operating_mode()
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
        
        # Уведомления о смене состояния рынка
        if self.market_was_open is not None:
            if is_open and not self.market_was_open:
                send_telegram_message("🔔 Market Opened")
                logger.info("[WORKER] Market opened")
            elif not is_open and self.market_was_open:
                send_telegram_message("🔔 Market Closed")
                logger.info("[WORKER] Market closed")
        
        self.market_was_open = is_open
        
        # Синхронизация только если рынок открыт (для LIVE)
        if operating_mode == 'live' and not is_open:
            logger.info("[WORKER] Market closed, Sync skipped")
            self.last_sync = datetime.now()
            status["last_sync"] = self.last_sync.isoformat()
            status["last_sync_result"] = "market_closed"
            save_worker_status(status)
            
            # Обновить GUI таймер даже при закрытом рынке
            update_gui_sync_status()
            return
        
        # ═══════════════════════════════════════════════════════════════
        # 4. Выполняем синхронизацию
        # ═══════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════


if __name__ == "__main__":
    # Настройка логера
    setup_logger(level="INFO", console=True)
    
    # Запуск worker
    worker = SyncWorker()
    worker.start()
