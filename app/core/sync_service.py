
# sync_service.py
# app.core.sync_service
#
# ════════════════════════════════════════════════════════════════════════════
# ⚠️ ВАЖНО: Auto Sync теперь работает через sync_worker.py (отдельный процесс)
# ════════════════════════════════════════════════════════════════════════════
#
# Методы start_auto_sync(), stop_auto_sync(), is_auto_sync_running() помечены
# как DEPRECATED и оставлены только для обратной совместимости.
#
# Новый способ управления Auto Sync:
#     from app.core.worker_client import start_worker, stop_worker, is_worker_running
#     
#     start_worker()      # Запустить
#     stop_worker()       # Остановить  
#     is_worker_running() # Проверить статус
#
# Этот файл по-прежнему содержит:
#     - run_manual_sync()      — ручная синхронизация
#     - execute_apply_now()    — Apply в Monitor режиме
#     - is_market_open_for_live() — проверка рынка
#     - get_auto_sync_clients()   — список клиентов
# ════════════════════════════════════════════════════════════════════════════

import os
import sys
import threading
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from app.core.logger import logger
from app.core.scheduler import EventScheduler
from app.core.json_utils import load_json, save_json
from pathlib import Path


# ════════════════════════════════════════════════════════════════
# [DEPRECATED] УПРАВЛЕНИЕ СПЯЩИМ РЕЖИМОМ WINDOWS
# ⚠️ Теперь реализовано в sync_worker.py
# ════════════════════════════════════════════════════════════════

def _prevent_sleep():
    """[DEPRECATED] Запретить компьютеру засыпать. Теперь в sync_worker.py."""
    if sys.platform == 'win32':
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            # Запрещает сон, но разрешает экрану гаснуть
            es_continuous_system = 0x80000001
            # noinspection PyUnresolvedReferences
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous_system)
            logger.info("[POWER] Sleep prevented - computer will stay awake")
        except (OSError, AttributeError) as e:
            logger.warning(f"[POWER] Failed to prevent sleep: {e}")


def _allow_sleep():
    """[DEPRECATED] Разрешить компьютеру засыпать. Теперь в sync_worker.py."""
    if sys.platform == 'win32':
        try:
            import ctypes
            # ES_CONTINUOUS - сбросить флаги, разрешить сон
            es_continuous = 0x80000000
            # noinspection PyUnresolvedReferences
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
            logger.info("[POWER] Sleep allowed - computer can sleep now")
        except (OSError, AttributeError) as e:
            logger.warning(f"[POWER] Failed to allow sleep: {e}")


# ════════════════════════════════════════════════════════════════
# ФАЙЛ СОСТОЯНИЯ AUTO SYNC (для восстановления после перезагрузки браузера)
# ════════════════════════════════════════════════════════════════

AUTO_SYNC_STATE_FILE = Path("config/auto_sync_state.json")
PENDING_MANUAL_SYNC_FLAG = Path("config/pending_manual_sync.flag")
MARKET_CLOSED_SENT_FILE = Path("config/market_closed_sent.txt")
MARKET_CALENDAR_FILE = Path("config/market_calendar.json")


def _load_auto_sync_state() -> dict:
    """Загрузить состояние Auto Sync из файла"""
    return load_json(str(AUTO_SYNC_STATE_FILE), default={
        "running": False,
        "started_at": None,
        "interval": "Every 5 minutes",
        "pid": None
    })


def _save_auto_sync_state(running: bool, interval: str = None):
    """Сохранить состояние Auto Sync в файл"""
    state = {
        "running": running,
        "started_at": datetime.now().isoformat() if running else None,
        "interval": interval,
        "pid": os.getpid() if running else None
    }
    save_json(str(AUTO_SYNC_STATE_FILE), state)
    logger.debug(f"Auto Sync state saved: running={running}")


def save_auto_sync_state(running: bool, interval: str = None):
    """Публичная обёртка для сохранения состояния Auto Sync"""
    _save_auto_sync_state(running, interval)


def is_auto_sync_running_from_file() -> bool:
    """
    [DEPRECATED] Проверить работает ли Auto Sync (из файла).
    
    ⚠️ Этот метод устарел! Используйте worker_client вместо него.
    
    Новый способ:
        from app.core.worker_client import is_worker_running
        is_worker_running()
    """
    state = _load_auto_sync_state()
    if not state.get("running"):
        return False
    
    # Проверить что процесс ещё жив
    pid = state.get("pid")
    if pid:
        # Проверка: это тот же процесс, что и текущий?
        current_pid = os.getpid()
        if pid == current_pid:
            # Тот же процесс — Auto Sync работает
            return True
        else:
            # Другой PID — процесс мог умереть или это старый файл.
            # Проверяем существование процесса (кросс-платформенно)
            if _is_process_running(pid):
                return True
            else:
                # Процесс умер, сбросить состояние
                _save_auto_sync_state(False)
                return False
    return False


def _is_process_running(pid: int) -> bool:
    """
    Проверить существует ли процесс с данным PID.
    Кросс-платформенная реализация (Windows + Linux).
    """
    import sys
    import subprocess
    
    if sys.platform == 'win32':
        # Windows: используем tasklist для проверки
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # Если PID найден, в output будет имя процесса
            return str(pid) in result.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    else:
        # Linux/Mac: используем os.kill(pid, 0)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def get_auto_sync_state() -> dict:
    """Получить текущее состояние Auto Sync из файла"""
    return _load_auto_sync_state()


class SyncService:
    """
    Сервис синхронизации позиций.
    
    Управляет:
    - Auto Sync (по расписанию через EventScheduler)
    - Manual Sync (однократный запуск)
    - Обновление Status (Last Sync, Next Sync In, Syncs Today)
    
    Режим (DRY RUN / LIVE) определяется из general_settings.json
    История сохраняется в synchronizer.py (не дублируется здесь)
    
    DRY RUN логика записи в историю:
    - Manual Sync: каждое нажатие = запись
    - Auto Sync: только первый запуск = запись, последующие итерации = пропуск
    """
    
    def __init__(self, client_manager=None):
        self.scheduler: Optional[EventScheduler] = None
        self._sync_task = None
        self._client_manager = client_manager
        self._auto_sync_first_logged = False  # Флаг: записана ли первая Auto Sync в DRY RUN
        self._sync_in_progress = False  # Флаг: выполняется ли sync сейчас
        self._sync_lock = threading.Lock()  # Блокировка для синхронизации
        self._settings_lock = threading.Lock()  # Блокировка для файла настроек
        
        # ═══════════════════════════════════════════════════════════════
        # Флаги-счётчики для отслеживания состояния рынка
        # ═══════════════════════════════════════════════════════════════
        self._market_open_iterations = 0    # Счётчик итераций когда биржа открыта
        self._market_closed_iterations = 0  # Счётчик итераций когда биржа закрыта
    
    def set_client_manager(self, client_manager) -> None:
        """Установить client_manager (публичный метод)"""
        if self._client_manager is None:
            self._client_manager = client_manager
        
    # ════════════════════════════════════════════════════════════════
    # НАСТРОЙКИ
    # ════════════════════════════════════════════════════════════════

    @staticmethod
    def _get_sync_settings_file() -> Path:
        """Путь к файлу настроек синхронизации"""
        return Path("config/sync_settings.json")

    @staticmethod
    def _get_sync_defaults() -> dict:
        """Настройки по умолчанию"""
        return {
            "auto_sync_all_enabled": True,
            "auto_selected_clients": [],
            "auto_sync_interval": "Every 5 minutes",
            "auto_sync_market_hours": True,
            "auto_sync_start_time": "09:30",
            "auto_sync_end_time": "16:00",
            "sync_all_enabled": True,
            "selected_clients": [],
            "last_sync_time": None,
            "syncs_today": 0,
            "syncs_today_date": None
        }
    
    def _load_sync_settings(self) -> dict:
        """Загрузить настройки (thread-safe)"""
        with self._settings_lock:
            return load_json(str(SyncService._get_sync_settings_file()), default=self._get_sync_defaults())
    
    def _save_sync_settings(self, settings: dict):
        """Сохранить настройки (thread-safe)"""
        with self._settings_lock:
            save_json(str(self._get_sync_settings_file()), settings)

    @staticmethod
    def _get_interval_seconds(interval_str: str) -> int:
        """Получить интервал в секундах"""
        intervals = {
            "Every 1 minute": 60,
            "Every 5 minutes": 300,
            "Every 15 minutes": 900,
            "Every 30 minutes": 1800,
            "Every hour": 3600
        }
        return intervals.get(interval_str, 300)

    @staticmethod
    def _get_operating_mode() -> str:
        """
        Получить operating_mode из general_settings.json.
        
        ВАЖНО: Читаем напрямую из файла, а не через ConfigCache,
        т.к. Auto Sync работает в фоновом потоке без доступа к st.session_state.
        """
        settings = load_json("config/general_settings.json", default={})
        return settings.get('operating_mode', 'monitor')

    @staticmethod
    def _get_monitor_sync_mode() -> str:
        """
        Получить monitor_sync_mode из general_settings.json.
        
        ВАЖНО: Читаем напрямую из файла, а не через ConfigCache,
        т.к. Auto Sync работает в фоновом потоке без доступа к st.session_state.
        """
        settings = load_json("config/general_settings.json", default={})
        return settings.get('monitor_sync_mode', 'simulation')

    @staticmethod
    def is_monitor_mode() -> bool:
        """Проверить находимся ли в режиме Monitor"""
        return SyncService._get_operating_mode() == 'monitor'
    
    # ════════════════════════════════════════════════════════════════
    # ПРОВЕРКА ACTIVE HOURS
    # ════════════════════════════════════════════════════════════════
    
    def is_within_active_hours(self) -> bool:
        """Проверить находимся ли в активных часах"""
        settings = self._load_sync_settings()
        
        if settings.get('auto_sync_market_hours', True):
            # Market hours: 9:30 AM - 4:00 PM ET
            # TODO: Добавить timezone conversion для ET
            now = datetime.now()
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            result = market_open <= now <= market_close
            logger.debug(f"[ACTIVE HOURS] Market Hours: {market_open.time()} - {market_close.time()}, "
                         f"now={now.time()}, within={result}")
            return result
        else:
            # Custom hours
            start_str = settings.get('auto_sync_start_time', '09:30')
            end_str = settings.get('auto_sync_end_time', '16:00')
            
            try:
                now = datetime.now()
                start_time = datetime.strptime(start_str, "%H:%M").time()
                end_time = datetime.strptime(end_str, "%H:%M").time()
                
                result = start_time <= now.time() <= end_time
                logger.debug(f"[ACTIVE HOURS] Custom: {start_str} - {end_str}, now={now.time()}, within={result}")
                return result
            except (ValueError, TypeError) as e:
                logger.warning(f"[ACTIVE HOURS] Error parsing times: {e}")
                return True
    
    def is_market_open_for_live(self) -> tuple:
        """
        Проверить открыт ли рынок для LIVE режима.
        
        Проверяет:
        1. Не выходной (Сб/Вс)
        2. Не праздник (из market_calendar.json)
        3. Время в пределах Active Hours
        4. Если early close — до 13:00 ET
        
        Returns:
            tuple: (is_open: bool, reason: str)
        """
        import pytz
        
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        today_str = now_et.strftime('%Y-%m-%d')
        
        # ═══════════════════════════════════════════════════════════════
        # 1. Проверка выходных
        # ═══════════════════════════════════════════════════════════════
        if now_et.weekday() >= 5:  # 5=Сб, 6=Вс
            day_name = "Saturday" if now_et.weekday() == 5 else "Sunday"
            logger.debug(f"[MARKET CHECK] Weekend: {day_name}")
            return False, f"Weekend ({day_name})"
        
        # ═══════════════════════════════════════════════════════════════
        # 2. Загрузить календарь
        # ═══════════════════════════════════════════════════════════════
        calendar = load_json(str(MARKET_CALENDAR_FILE), default={})
        
        # ═══════════════════════════════════════════════════════════════
        # 3. Проверка праздников
        # ═══════════════════════════════════════════════════════════════
        holidays = calendar.get('holidays', [])
        for holiday in holidays:
            if holiday.get('date') == today_str:
                holiday_name = holiday.get('name', 'Holiday')
                logger.debug(f"[MARKET CHECK] Holiday: {holiday_name}")
                return False, f"Holiday ({holiday_name})"
        
        # ═══════════════════════════════════════════════════════════════
        # 4. Определить время закрытия (early close или обычное)
        # ═══════════════════════════════════════════════════════════════
        close_time_str = "16:00"  # По умолчанию
        early_close_name = None
        
        early_closes = calendar.get('early_close', [])
        for early in early_closes:
            if early.get('date') == today_str:
                close_time_str = early.get('close_time', '13:00')
                early_close_name = early.get('name', 'Early Close')
                logger.debug(f"[MARKET CHECK] Early close: {early_close_name} at {close_time_str}")
                break
        
        # ═══════════════════════════════════════════════════════════════
        # 5. Проверка Active Hours (с учётом early close)
        # ═══════════════════════════════════════════════════════════════
        settings = self._load_sync_settings()
        
        # Время открытия
        if settings.get('auto_sync_market_hours', True):
            open_time_str = "09:30"
        else:
            open_time_str = settings.get('auto_sync_start_time', '09:30')
        
        # Время закрытия (early close имеет приоритет)
        if early_close_name:
            # Early close — использовать время из календаря
            pass  # close_time_str уже установлен выше
        elif settings.get('auto_sync_market_hours', True):
            close_time_str = "16:00"
        else:
            close_time_str = settings.get('auto_sync_end_time', '16:00')
        
        try:
            open_time = datetime.strptime(open_time_str, "%H:%M").time()
            close_time = datetime.strptime(close_time_str, "%H:%M").time()
            current_time = now_et.time()
            
            if current_time < open_time:
                logger.debug(f"[MARKET CHECK] Before market open: {current_time} < {open_time}")
                return False, f"Before market open ({open_time_str} ET)"
            
            if current_time > close_time:
                if early_close_name:
                    logger.debug(f"[MARKET CHECK] After early close: {current_time} > {close_time}")
                    return False, f"After early close ({close_time_str} ET - {early_close_name})"
                else:
                    logger.debug(f"[MARKET CHECK] After market close: {current_time} > {close_time}")
                    return False, f"After market close ({close_time_str} ET)"
            
            logger.debug(f"[MARKET CHECK] Market OPEN: {open_time_str} - {close_time_str} ET")
            return True, "Market open"
            
        except (ValueError, TypeError) as e:
            logger.warning(f"[MARKET CHECK] Error parsing times: {e}")
            return True, "Error checking (allowing)"
    
    # ════════════════════════════════════════════════════════════════
    # ПОЛУЧЕНИЕ СПИСКА КЛИЕНТОВ
    # ════════════════════════════════════════════════════════════════

    def get_auto_sync_clients(self) -> List[str]:
        """Получить список клиентов для Auto Sync"""
        settings = self._load_sync_settings()

        # Использовать сохраненный client_manager
        if self._client_manager is None:
            return []

        if settings.get('auto_sync_all_enabled', True):
            return [c.id for c in self._client_manager.get_enabled_clients()]
        else:
            return settings.get('auto_selected_clients', [])
    
    def get_manual_sync_clients(self) -> List[str]:
        """Получить список клиентов для Manual Sync"""
        settings = self._load_sync_settings()
        
        # Использовать сохраненный client_manager (не session_state - недоступен в фоновом потоке)
        if self._client_manager is None:
            return []
        
        if settings.get('sync_all_enabled', True):
            return [c.id for c in self._client_manager.get_enabled_clients()]
        else:
            return settings.get('selected_clients', [])
    
    # ════════════════════════════════════════════════════════════════
    # ОБНОВЛЕНИЕ STATUS
    # ════════════════════════════════════════════════════════════════
    
    def update_sync_status(self):
        """Обновить статус после синхронизации (thread-safe)"""
        with self._settings_lock:
            settings = load_json(str(SyncService._get_sync_settings_file()), default=self._get_sync_defaults())
            
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            
            # Обновить время последней синхронизации
            settings['last_sync_time'] = now.isoformat()
            
            # Рассчитать и сохранить время следующей синхронизации
            interval_str = settings.get('auto_sync_interval', 'Every 5 minutes')
            interval_sec = self._get_interval_seconds(interval_str)
            next_sync = now + timedelta(seconds=interval_sec)
            settings['next_sync_time'] = next_sync.isoformat()
            
            # Обновить счетчик за день
            if settings.get('syncs_today_date') != today_str:
                settings['syncs_today'] = 1
                settings['syncs_today_date'] = today_str
            else:
                settings['syncs_today'] = settings.get('syncs_today', 0) + 1
            
            save_json(str(self._get_sync_settings_file()), settings)
            logger.info(f"Sync status updated: syncs_today={settings['syncs_today']}")
    
    def _update_next_sync_time(self):
        """Обновить статус после Monitor delta tracking (thread-safe)"""
        with self._settings_lock:
            settings = load_json(str(SyncService._get_sync_settings_file()), default=self._get_sync_defaults())
            
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            
            # Обновить время последней синхронизации
            settings['last_sync_time'] = now.isoformat()
            
            # Рассчитать и сохранить время следующей синхронизации
            interval_str = settings.get('auto_sync_interval', 'Every 5 minutes')
            interval_sec = self._get_interval_seconds(interval_str)
            next_sync = now + timedelta(seconds=interval_sec)
            settings['next_sync_time'] = next_sync.isoformat()
            
            # Обновить счетчик за день
            if settings.get('syncs_today_date') != today_str:
                settings['syncs_today'] = 1
                settings['syncs_today_date'] = today_str
            else:
                settings['syncs_today'] = settings.get('syncs_today', 0) + 1
            
            save_json(str(self._get_sync_settings_file()), settings)
    
    # ════════════════════════════════════════════════════════════════
    # СИНХРОНИЗАЦИЯ
    # ════════════════════════════════════════════════════════════════

    def _perform_sync(self, client_ids: List[str], source: str = "manual") -> Dict[str, Any]:
        """
        Выполнить синхронизацию.
        
        Режим (DRY RUN / LIVE) определяется из general_settings.json
        История сохраняется в synchronizer.py
        
        DRY RUN логика записи:
        - Manual Sync: каждый раз записывать
        - Auto Sync: только первый запуск записывать
        """
        # Определить режим
        operating_mode = self._get_operating_mode()
        monitor_sync_mode = self._get_monitor_sync_mode()
        
        mode_icons = {
            'monitor': f"🔍 MONITOR ({monitor_sync_mode.upper()})",
            'simulation': "🔶 SIMULATION",
            'live': "🔴 LIVE"
        }
        mode_str = mode_icons.get(operating_mode, "UNKNOWN")
        
        # Краткий лог начала
        logger.info(f"{mode_str} {source} sync | {len(client_ids)} clients")

        # ═══════════════════════════════════════════════════════════════
        # LIVE РЕЖИМ: Проверка рабочих часов рынка (только для Manual Sync)
        # Для Auto Sync проверка уже сделана в _auto_sync_task
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'live' and source == "manual":
            is_open, reason = self.is_market_open_for_live()
            if not is_open:
                # Рынок закрыт — только обновить кэш
                from app.core.cache_manager import update_all_cache_background
                update_all_cache_background()
                
                logger.info(f"🔴 LIVE (Sync) sync cancelled. Market closed: {reason}")
                
                return {
                    "status": "market_closed",
                    "reason": reason,
                    "cache_updated": True
                }
            else:
                # Рынок открыт — полная синхронизация
                logger.info(f"🔴 LIVE (Sync): Market OPEN. Executing sync")
        
        # В SIMULATION — DEBUG уровень (игнорировать часы для тестирования)
        if operating_mode == 'simulation' and not self.is_within_active_hours():
            logger.debug(f"Outside active hours, continuing for SIMULATION testing")

        if not client_ids:
            logger.warning("No clients to sync")
            return {"status": "skipped", "reason": "no_clients"}

        try:
            # Получить main client
            from app.core.config import get_main_client
            main_client = get_main_client()

            if not main_client:
                logger.error("❌ Main account not authorized")
                return {"status": "error", "reason": "main_not_authorized"}

            # Получить client_manager
            client_manager = self._client_manager

            # ════════════════════════════════════════════════════════════════
            # MONITOR РЕЖИМ: Auto Sync только отслеживает дельту
            # ════════════════════════════════════════════════════════════════
            
            if operating_mode == 'monitor' and source == "auto":
                # Обновить кэш для актуальных данных в таблицах
                from app.core.cache_manager import update_all_cache_background
                update_all_cache_background()
                
                # Проверить рынок для Monitor Live Delta
                if monitor_sync_mode == 'live':
                    is_open, reason = self.is_market_open_for_live()
                    if not is_open:
                        logger.info(f"🔍 🔴 Monitor Live Delta: Market closed. {reason}")
                    else:
                        logger.info(f"🔍 🔴 Monitor Live Delta: Market OPEN. Full monitoring active")
                
                # В Monitor режиме Auto Sync только отслеживает изменения дельты
                from app.core.delta_tracker import get_delta_tracker
                from app.models.copier.multi_sync import MultiSynchronizer
                
                delta_tracker = get_delta_tracker()
                
                # Создать synchronizer для расчёта дельты (без выполнения)
                multi_sync = MultiSynchronizer(
                    main_client=main_client,
                    client_manager=client_manager,
                    operating_mode='simulation'  # Для расчёта дельты
                )
                
                results = {}
                for client_id in client_ids:
                    try:
                        # Получить дельту для клиента
                        client = client_manager.get_client(client_id)
                        if not client:
                            continue
                        
                        delta_result = multi_sync.calculate_delta_for_client(client)
                        if delta_result:
                            deltas = delta_result.get('deltas', {})
                            prices = delta_result.get('prices', {})
                            
                            # Отследить изменения
                            changed, reason, changes = delta_tracker.track_delta(
                                client_id, deltas, prices
                            )
                            
                            results[client_id] = {
                                'status': 'tracked',
                                'changed': changed,
                                'reason': reason,
                                'delta_count': len(deltas)
                            }
                            
                            # Если дельта изменилась — отправить уведомление
                            if changed and changes:
                                SyncService._send_delta_notification(client.name, deltas, prices, changes)
                        else:
                            results[client_id] = {'status': 'no_delta'}
                            
                    except Exception as e:
                        logger.error(f"🔍 Error tracking {client_id}: {e}")
                        results[client_id] = {'status': 'error', 'error': str(e)}
                
                # Компактный итоговый лог
                settings = self._load_sync_settings()
                syncs_today = settings.get('syncs_today', 0) + 1
                interval_str = settings.get('auto_sync_interval', 'Every 5 minutes')
                logger.info(f"{'═' * 50}")
                logger.info(f"🔍 MONITOR done | Next: {interval_str.replace('Every ', '')} | Today: {syncs_today}")
                
                # Обновить next_sync_time для UI
                self._update_next_sync_time()
                
                return results

            # ════════════════════════════════════════════════════════════════
            # ОБЫЧНЫЙ SYNC (Simulation, Live, или Monitor Manual)
            # ════════════════════════════════════════════════════════════════

            # SIMULATION: Обновить реальный кэш на каждой итерации
            if operating_mode == 'simulation' and source == "auto":
                from app.core.cache_manager import update_all_cache_background, update_dry_cache_prices
                update_all_cache_background()
                # Обновить цены и P&L в dry cache
                update_dry_cache_prices()

            # Импортировать MultiSynchronizer
            from app.models.copier.multi_sync import MultiSynchronizer

            # Определить skip_history
            skip_history = False
            if operating_mode == 'simulation' and source == "auto":
                if self._auto_sync_first_logged:
                    skip_history = True
                    logger.info(f"📝 {mode_str} Auto Sync: skipping history (not first run)")
                else:
                    # Первый запуск — записать и установить флаг
                    self._auto_sync_first_logged = True
                    logger.info(f"📝 {mode_str} Auto Sync: writing history (first run)")
            
            # Для Monitor Manual Sync — использовать monitor_sync_mode
            effective_mode = None
            if operating_mode == 'monitor' and source == "manual":
                effective_mode = monitor_sync_mode
                logger.info(f"[MONITOR] Manual Sync using mode: {effective_mode.upper()}")

            # Создать synchronizer (режим определяется автоматически из настроек)
            multi_sync = MultiSynchronizer(
                main_client=main_client,
                client_manager=client_manager,
                operating_mode=effective_mode  # None = читать из general_settings.json
            )

            # Выполнить синхронизацию
            results = multi_sync.sync_all(selected_clients=client_ids, skip_history=skip_history)

            # Обновить статус (Last Sync, Syncs Today)
            self.update_sync_status()

            logger.info(f"Sync completed: {len(results)} clients processed")

            # ═══════════════════════════════════════════════════════════════
            # TELEGRAM уведомление (если были ордера)
            # ═══════════════════════════════════════════════════════════════
            # Использовать effective_mode если установлен, иначе operating_mode
            telegram_mode = effective_mode if effective_mode else operating_mode
            
            if telegram_mode in ('simulation', 'live'):
                sync_type = "Auto Sync" if source == "auto" else "Sync"
                self._send_telegram_positions_synced(results, telegram_mode, sync_type)

            # Toast уведомления обрабатываются в sidebar.py для Manual Sync
            # и в _auto_sync_task для Auto Sync

            return results

        except Exception as e:
            logger.exception(f"Sync error: {e}")
            return {"status": "error", "reason": str(e)}
    
    # ════════════════════════════════════════════════════════════════
    # MANUAL SYNC
    # ════════════════════════════════════════════════════════════════
    
    def run_manual_sync(self) -> Dict[str, Any]:
        """
        Запустить Manual Sync (однократно).
        
        Для LIVE и SIMULATION:
        1. Обновить account_cache.json
        2. Проверить биржу
        3. Если открыта → синхронизация
        4. Если закрыта → только Toast + лог
        """
        from app.core.cache_manager import update_all_cache_background
        
        operating_mode = self._get_operating_mode()
        
        # ═══════════════════════════════════════════════════════════════
        # Шаг 2-3: Обновить account_cache.json
        # ═══════════════════════════════════════════════════════════════
        update_all_cache_background()
        logger.info("[MANUAL SYNC] account_cache updated")
        
        # ═══════════════════════════════════════════════════════════════
        # LIVE режим: Проверка биржи
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'live':
            is_open, reason = self.is_market_open_for_live()
            
            if is_open:
                # Биржа ОТКРЫТА — синхронизация
                logger.info("[MANUAL SYNC] 🔴 Market is open, sync started")
                
                client_ids = self.get_manual_sync_clients()
                result = self._perform_sync(client_ids, source="manual")
                
                # Проверить были ли ордера (дельта ≠ 0)
                has_orders = self._check_sync_had_orders(result)
                
                if not has_orders:
                    # Дельта = 0 — только лог, без Telegram
                    logger.info("[MANUAL SYNC] 🔴 Positions are synchronized, no orders needed")
                
                # Если были ордера - уведомления отправлены в _send_telegram_positions_synced
                
                return result
            else:
                # Биржа ЗАКРЫТА — только Toast + лог
                logger.info(f"[MANUAL SYNC] 🔴 Market is closed, sync suspended. {reason}")
                self._send_toast_market_closed()
                
                return {"status": "skipped", "reason": reason}
        
        # ═══════════════════════════════════════════════════════════════
        # SIMULATION режим: Проверка биржи
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'simulation':
            # Шаг 5: Скопировать account_cache_dry.json = account_cache.json (полная копия)
            from app.core.cache_manager import copy_cache_to_dry
            copy_cache_to_dry()
            logger.info("[MANUAL SYNC] 🔶 account_cache_dry.json = account_cache.json (full copy)")
            
            # Шаг 6: Проверить биржу
            is_open = self.is_within_active_hours()
            
            if is_open:
                # Биржа ОТКРЫТА — синхронизация
                logger.info("[MANUAL SYNC] 🔶 Market is open, sync started")
                
                client_ids = self.get_manual_sync_clients()
                result = self._perform_sync(client_ids, source="manual")
                
                # Проверить были ли ордера (дельта ≠ 0)
                has_orders = self._check_sync_had_orders(result)
                
                if not has_orders:
                    # Дельта = 0 — только лог, без Telegram
                    logger.info("[MANUAL SYNC] 🔶 Positions are synchronized, no orders needed")
                
                # Если были ордера - уведомления отправлены в _send_telegram_positions_synced
                
                return result
            else:
                # Биржа ЗАКРЫТА — только Toast + лог
                logger.info("[MANUAL SYNC] 🔶 Market is closed, sync suspended.")
                self._send_toast_market_closed()
                
                return {"status": "skipped", "reason": "Market closed"}
        
        # ═══════════════════════════════════════════════════════════════
        # Другие режимы (Monitor и т.д.)
        # ═══════════════════════════════════════════════════════════════
        client_ids = self.get_manual_sync_clients()
        return self._perform_sync(client_ids, source="manual")

    @staticmethod
    def _check_sync_had_orders(results: Dict[str, Any]) -> bool:
        """Проверить были ли ордера в результатах синхронизации"""
        if not isinstance(results, dict):
            return False
        
        for client_id, client_result in results.items():
            if not isinstance(client_result, dict):
                continue
            if client_result.get('status') != 'success':
                continue
            
            result = client_result.get('result', {})
            orders_count = result.get('summary', {}).get('orders_placed', 0)
            
            if orders_count > 0:
                return True
        
        return False
    
    def execute_apply_now(self) -> Dict[str, Any]:
        """
        Выполнить Apply немедленно.
        
        Использует блокировку, чтобы дождаться завершения текущего sync.
        
        Returns:
            Результат синхронизации
        """
        logger.info("[APPLY] Execute apply now requested")
        
        # Дождаться завершения текущего sync (если выполняется)
        with self._sync_lock:
            logger.info("[APPLY] Executing manual sync")
            result = self.run_manual_sync()
        
        return result
    
    # ════════════════════════════════════════════════════════════════
    # [DEPRECATED] AUTO SYNC (с планировщиком)
    # ⚠️ Теперь реализовано в sync_worker.py
    # Оставлено для обратной совместимости
    # ════════════════════════════════════════════════════════════════
    
    def _auto_sync_task(self):
        """
        [DEPRECATED] Задача для периодической синхронизации.
        ⚠️ Теперь реализовано в sync_worker.py
        
        Алгоритм для LIVE режима:
        1. Обновить account_cache.json
        2. Проверить биржу (открыта/закрыта)
        3. Если открыта → синхронизация
        4. Если закрыта → только лог
        5. Telegram уведомления при смене состояния
        """
        # Использовать блокировку чтобы Apply мог дождаться завершения
        with self._sync_lock:
            self._sync_in_progress = True
            try:
                logger.info("Auto sync task triggered")
                
                # Проверить pending_manual_sync В НАЧАЛЕ (если был установлен между циклами)
                if self._check_pending_manual_sync():
                    self._clear_pending_manual_sync()
                    logger.info("[PENDING] Executing queued manual sync (before auto)")
                    self.run_manual_sync()
                
                operating_mode = self._get_operating_mode()
                
                # ═══════════════════════════════════════════════════════════════
                # Шаг 3.1-3.2: Обновить account_cache.json
                # ═══════════════════════════════════════════════════════════════
                from app.core.cache_manager import update_all_cache_background
                update_all_cache_background()
                logger.info("[AUTO SYNC] account_cache updated")
                
                # ═══════════════════════════════════════════════════════════════
                # LIVE РЕЖИМ: Логика с флагами
                # ═══════════════════════════════════════════════════════════════
                if operating_mode == 'live':
                    is_open, reason = self.is_market_open_for_live()
                    
                    if is_open:
                        # ═══════════════════════════════════════════════════════
                        # Биржа ОТКРЫТА
                        # ═══════════════════════════════════════════════════════
                        
                        # Проверить смену состояния: была закрыта → открылась
                        if self._market_open_iterations == 0 and self._market_closed_iterations > 0:
                            # Биржа только что открылась
                            self._send_toast_market_opened()
                            self._send_telegram_market_opened()
                            self._market_closed_iterations = 0
                        
                        if self._market_open_iterations == 0:
                            # Первая итерация с открытой биржей
                            self._market_open_iterations = 1
                            logger.info("[AUTO SYNC] 🔴 The market is open, synchronization is enabled.")
                        else:
                            self._market_open_iterations += 1
                        
                        # Выполнить синхронизацию
                        client_ids = self.get_auto_sync_clients()
                        self._perform_sync(client_ids, source="auto")
                    
                    else:
                        # ═══════════════════════════════════════════════════════
                        # Биржа ЗАКРЫТА
                        # ═══════════════════════════════════════════════════════
                        
                        # Проверить смену состояния: была открыта → закрылась
                        if self._market_closed_iterations == 0 and self._market_open_iterations > 0:
                            # Биржа только что закрылась
                            self._send_toast_market_closed()
                            self._send_telegram_market_closed_until()
                            self._market_open_iterations = 0
                        
                        if self._market_closed_iterations == 0:
                            # Первая итерация с закрытой биржей
                            self._market_closed_iterations = 1
                        else:
                            self._market_closed_iterations += 1
                        
                        logger.info(f"[AUTO SYNC] 🔴 The market is closed, synchronization is suspended. {reason}")
                
                # ═══════════════════════════════════════════════════════════════
                # SIMULATION РЕЖИМ: Логика с флагами (аналогично LIVE)
                # ═══════════════════════════════════════════════════════════════
                elif operating_mode == 'simulation':
                    is_open = self.is_within_active_hours()
                    
                    if is_open:
                        # ═══════════════════════════════════════════════════════
                        # Биржа ОТКРЫТА
                        # ═══════════════════════════════════════════════════════
                        
                        # Проверить смену состояния: была закрыта → открылась
                        if self._market_open_iterations == 0 and self._market_closed_iterations > 0:
                            # Биржа только что открылась
                            self._send_toast_market_opened()
                            self._send_telegram_market_opened()
                            self._market_closed_iterations = 0
                        
                        if self._market_open_iterations == 0:
                            # Первая итерация с открытой биржей
                            self._market_open_iterations = 1
                            logger.info("[AUTO SYNC] 🔶 The market is open, synchronization is enabled.")
                            # init_simulation_cache() уже вызван при Start (в start_auto_sync)
                        else:
                            self._market_open_iterations += 1
                        
                        # Выполнить синхронизацию
                        client_ids = self.get_auto_sync_clients()
                        self._perform_sync(client_ids, source="auto")
                    
                    else:
                        # ═══════════════════════════════════════════════════════
                        # Биржа ЗАКРЫТА
                        # ═══════════════════════════════════════════════════════
                        
                        # Проверить смену состояния: была открыта → закрылась
                        if self._market_closed_iterations == 0 and self._market_open_iterations > 0:
                            # Биржа только что закрылась
                            self._send_toast_market_closed()
                            self._send_telegram_market_closed_until()
                            self._market_open_iterations = 0
                        
                        if self._market_closed_iterations == 0:
                            # Первая итерация с закрытой биржей
                            self._market_closed_iterations = 1
                        else:
                            self._market_closed_iterations += 1
                        
                        logger.info("[AUTO SYNC] 🔶 The market is closed, synchronization is suspended.")
                
                # ═══════════════════════════════════════════════════════════════
                # Другие режимы (Monitor и т.д.): стандартная логика
                # ═══════════════════════════════════════════════════════════════
                elif operating_mode not in ('live', 'simulation'):
                    client_ids = self.get_auto_sync_clients()
                    self._perform_sync(client_ids, source="auto")
                
                # Проверить pending_manual_sync ПОСЛЕ (если был установлен во время sync)
                if self._check_pending_manual_sync():
                    self._clear_pending_manual_sync()
                    logger.info("[PENDING] Executing queued manual sync (after auto)")
                    self.run_manual_sync()
            finally:
                self._sync_in_progress = False
    
    def _check_and_send_market_closed(self, operating_mode: str):
        """
        Проверить закрытие рынка и отправить Telegram уведомление.
        
        Используется для SIMULATION режима.
        Для LIVE режима логика в _auto_sync_task.
        """
        try:
            # Для LIVE используем новую логику в _auto_sync_task
            if operating_mode == 'live':
                return
            
            # ═══════════════════════════════════════════════════════════════
            # SIMULATION: Проверка Active Hours
            # ═══════════════════════════════════════════════════════════════
            within_hours = self.is_within_active_hours()
            
            logger.debug(f"[MARKET CLOSED CHECK] within_hours={within_hours}")
            
            if within_hours:
                # Рынок ещё открыт — сбросить флаг отправки (если был)
                if MARKET_CLOSED_SENT_FILE.exists():
                    MARKET_CLOSED_SENT_FILE.unlink()
                logger.debug("[MARKET CLOSED CHECK] Market still open, waiting...")
                return
            
            # ═══════════════════════════════════════════════════════════════
            # Рынок закрылся! Проверить отправляли ли уже
            # ═══════════════════════════════════════════════════════════════
            from datetime import datetime
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            if MARKET_CLOSED_SENT_FILE.exists():
                sent_date = MARKET_CLOSED_SENT_FILE.read_text().strip()
                if sent_date == today_str:
                    # Уже отправляли сегодня
                    logger.debug("[MARKET CLOSED CHECK] Already sent today, skipping")
                    return
            
            # ═══════════════════════════════════════════════════════════════
            # Отправить уведомления Market Closed
            # ═══════════════════════════════════════════════════════════════
            logger.info("[TELEGRAM] Market closed detected, sending notifications")
            # 1. Итоги дня
            self._send_telegram_market_closed_summary(operating_mode)
            # 2. Биржа закрыта
            self._send_telegram_market_closed_until()
            
            # Записать дату отправки
            MARKET_CLOSED_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
            MARKET_CLOSED_SENT_FILE.write_text(today_str)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Error checking market closed: {e}")
    
    # ════════════════════════════════════════════════════════════════
    # TELEGRAM УВЕДОМЛЕНИЯ ДЛЯ SYNC
    # ════════════════════════════════════════════════════════════════

    @staticmethod
    def _send_telegram_sync_status(operating_mode: str, sync_type: str, action: str = None):
        """
        Отправить Telegram уведомление о статусе синхронизации.
        Главная функция (всегда работает если Telegram включен).
        
        Args:
            operating_mode: 'live', 'simulation', 'monitor_live', 'monitor_simulation'
            sync_type: 'auto' или 'manual'
            action: 'started', 'stopped', 'completed' или None (без action)
        """
        try:
            from app.core.telegram_service import get_telegram_service
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                return
            
            telegram.notify_sync_status(
                operating_mode=operating_mode,
                sync_type=sync_type,
                action=action
            )
            logger.info(f"[TELEGRAM] Sync status sent: {operating_mode}/{sync_type}/{action}")
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send sync status: {e}")

    @staticmethod
    def _send_telegram_market_opened():
        """Отправить Telegram: биржа открылась"""
        try:
            from app.core.telegram_service import get_telegram_service
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                return
            
            telegram.notify_market_opened()
            logger.info("[TELEGRAM] notify_market_opened sent")
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send market opened: {e}")

    @staticmethod
    def _send_telegram_market_closed_until():
        """Отправить Telegram: биржа закрыта, откроется..."""
        try:
            from app.core.telegram_service import get_telegram_service, get_next_market_open
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                return
            
            # Получить время следующего открытия
            opens_at, _ = get_next_market_open()
            
            telegram.notify_market_closed_until(opens_at=opens_at)
            logger.info("[TELEGRAM] notify_market_closed_until sent")
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send market closed until: {e}")

    @staticmethod
    def _send_telegram_market_closed_summary(operating_mode: str):
        """Отправить Telegram: итоги дня (данные аккаунтов)"""
        try:
            from app.core.telegram_service import get_telegram_service
            from app.core.cache_manager import get_cache, get_simulation_cache
            from app.core.config_cache import ConfigCache
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                return
            
            # ═══════════════════════════════════════════════════════════════
            # Main Account - ВСЕГДА из обычного кэша
            # ═══════════════════════════════════════════════════════════════
            cache = get_cache()
            main_account = cache.get('main_account', {})
            
            main_total = main_account.get('balances', {}).get('liquidation_value', 0)
            main_pl = 0.0
            main_positions_value = 0.0
            
            for pos in main_account.get('positions', []):
                qty = pos.get('quantity', 0)
                price = pos.get('price', 0)
                main_positions_value += qty * price
                main_pl += pos.get('unrealized_pl', 0)
            
            if main_total == 0:
                main_total = main_positions_value
            
            # ═══════════════════════════════════════════════════════════════
            # Clients
            # ═══════════════════════════════════════════════════════════════
            if operating_mode == 'simulation':
                dry_cache = get_simulation_cache()
                clients_cache = dry_cache.get('clients', {})
            else:
                clients_cache = cache.get('clients', {})
            
            clients_data = []
            
            # Получить имена клиентов из clients.json
            clients_config = ConfigCache.get_clients()
            client_names = {}
            if isinstance(clients_config, dict):
                slave_accounts = clients_config.get('slave_accounts', [])
                for acc in slave_accounts:
                    if isinstance(acc, dict):
                        cid = acc.get('id', '')
                        client_names[cid] = acc.get('name', cid)
            elif isinstance(clients_config, list):
                for c in clients_config:
                    if isinstance(c, dict):
                        cid = c.get('id', '')
                        client_names[cid] = c.get('name', cid)
            
            for client_id, client_cache in clients_cache.items():
                client_name = client_names.get(client_id, client_id)
                
                client_total = client_cache.get('balances', {}).get('liquidation_value', 0)
                client_pl = 0.0
                client_positions_value = 0.0
                
                for pos in client_cache.get('positions', []):
                    qty = pos.get('quantity', 0)
                    price = pos.get('price', 0)
                    client_positions_value += qty * price
                    client_pl += pos.get('unrealized_pl', 0)
                
                if client_total == 0:
                    client_total = client_positions_value
                
                clients_data.append({
                    'name': client_name,
                    'total': client_total,
                    'positions_value': client_positions_value,
                    'pl': client_pl
                })
            
            # Отправить уведомление
            telegram.notify_market_closed_summary(
                main_total=main_total,
                main_pl=main_pl,
                main_positions_value=main_positions_value,
                clients_data=clients_data
            )
            
            logger.info("[TELEGRAM] Market closed summary sent")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send market closed summary: {e}")
    
    # ════════════════════════════════════════════════════════════════
    # TOAST УВЕДОМЛЕНИЯ ДЛЯ LIVE РЕЖИМА
    # ════════════════════════════════════════════════════════════════

    @staticmethod
    def _send_toast_market_opened():
        """Toast: биржа открыта"""
        try:
            from app.core.sync_common import get_notification_settings
            from app.core.notification_service import get_notification_service
            
            notif_settings = get_notification_settings()
            if notif_settings.get('toast_on_success', False):
                notif = get_notification_service()
                notif.info("🔔 The market is open. Sync is enabled.")
        except Exception as e:
            logger.error(f"[TOAST] Failed to send market opened toast: {e}")

    @staticmethod
    def _send_toast_market_closed():
        """Toast: биржа закрыта"""
        try:
            from app.core.sync_common import get_notification_settings
            from app.core.notification_service import get_notification_service
            
            notif_settings = get_notification_settings()
            if notif_settings.get('toast_on_success', False):
                notif = get_notification_service()
                notif.info("🔒 Market closed. Sync is suspended.")
        except Exception as e:
            logger.error(f"[TOAST] Failed to send market closed toast: {e}")

    @staticmethod
    def _check_pending_manual_sync() -> bool:
        """Проверить флаг pending_manual_sync из файла"""
        return PENDING_MANUAL_SYNC_FLAG.exists()

    @staticmethod
    def _clear_pending_manual_sync():
        """Удалить флаг pending_manual_sync"""
        if PENDING_MANUAL_SYNC_FLAG.exists():
            PENDING_MANUAL_SYNC_FLAG.unlink()
            logger.debug("Pending manual sync flag cleared")

    @staticmethod
    def set_pending_manual_sync():
        """Установить флаг pending_manual_sync"""
        PENDING_MANUAL_SYNC_FLAG.parent.mkdir(parents=True, exist_ok=True)
        PENDING_MANUAL_SYNC_FLAG.touch()
        logger.info("[PENDING] Manual sync queued")
    
    def start_auto_sync(self) -> bool:
        """
        [DEPRECATED] Запустить Auto Sync через фоновый поток.
        
        ⚠️ Этот метод устарел! Используйте sync_worker.py вместо него.
        Оставлен для обратной совместимости.
        
        Новый способ:
            from app.core.worker_client import start_worker
            start_worker()
        """
        logger.warning("[DEPRECATED] start_auto_sync() is deprecated. Use sync_worker.py instead.")
        try:
            # Запретить компьютеру засыпать
            _prevent_sleep()
            
            # Сбросить флаг первого запуска DRY RUN (новая сессия)
            self._auto_sync_first_logged = False
            
            # ═══════════════════════════════════════════════════════════════
            # Инициализировать флаги-счётчики
            # ═══════════════════════════════════════════════════════════════
            self._market_open_iterations = 0
            self._market_closed_iterations = 0
            
            # ═══════════════════════════════════════════════════════════════
            # SIMULATION: Инициализировать dry cache при старте
            # ═══════════════════════════════════════════════════════════════
            operating_mode = self._get_operating_mode()
            if operating_mode == 'simulation':
                # Сначала обновить реальный кэш из API
                from app.core.cache_manager import update_all_cache_background, init_simulation_cache
                update_all_cache_background()
                # Затем создать dry cache на основе обновлённых данных
                init_simulation_cache()
            
            # Сбросить флаг отправки Market Closed (новая сессия)
            if MARKET_CLOSED_SENT_FILE.exists():
                MARKET_CLOSED_SENT_FILE.unlink()
                logger.debug("[AUTO SYNC] Market closed sent flag reset")
            
            # Создать планировщик если нет
            if self.scheduler is None:
                self.scheduler = EventScheduler()
            
            # Запустить планировщик если не запущен
            if not self.scheduler.is_running():
                self.scheduler.start()
            
            # Отменить предыдущую задачу если есть
            if self._sync_task:
                self.scheduler.cancel(self._sync_task)
            
            # Получить интервал
            settings = self._load_sync_settings()
            interval_str = settings.get('auto_sync_interval', 'Every 5 minutes')
            interval_sec = self._get_interval_seconds(interval_str)
            
            # Установить начальное next_sync_time ПЕРЕД запуском задачи
            now = datetime.now()
            settings['next_sync_time'] = now.isoformat()
            self._save_sync_settings(settings)
            
            # Сохранить состояние в файл (для восстановления после перезагрузки браузера)
            _save_auto_sync_state(running=True, interval=interval_str)
            
            # Запланировать периодическую задачу
            # Первый запуск через 1 секунду (чтобы избежать race condition с файлом)
            self._sync_task = self.scheduler.schedule_every(
                interval=interval_sec,
                func=self._auto_sync_task,
                delay_first=1,  # Запустить через 1 сек (избежать race condition)
                name="auto_sync"
            )
            
            # Логировать режим
            operating_mode = self._get_operating_mode()
            monitor_sync_mode = self._get_monitor_sync_mode()
            mode_icons = {
                'monitor': f"MONITOR 🔍 ({monitor_sync_mode.upper()})",
                'simulation': "SIMULATION 🔶",
                'live': "LIVE 🔴"
            }
            mode_str = mode_icons.get(operating_mode, "UNKNOWN")
            logger.info(f"Auto Sync started: {interval_str} ({interval_sec}s), mode: {mode_str}")
            
            # ═══════════════════════════════════════════════════════════════
            # Telegram: notify_sync_status(started) для Live и Simulation
            # ═══════════════════════════════════════════════════════════════
            if operating_mode in ('live', 'simulation'):
                self._send_telegram_sync_status(operating_mode, 'auto', 'started')
            
            return True
            
        except Exception as e:
            logger.exception(f"Failed to start Auto Sync: {e}")
            return False
    
    def stop_auto_sync(self):
        """
        [DEPRECATED] Остановить Auto Sync (фоновый поток).
        
        ⚠️ Этот метод устарел! Используйте sync_worker.py вместо него.
        
        Новый способ:
            from app.core.worker_client import stop_worker
            stop_worker()
        """
        logger.warning("[DEPRECATED] stop_auto_sync() is deprecated. Use sync_worker.py instead.")
        try:
            # ═══════════════════════════════════════════════════════════════
            # Отправить Telegram уведомление перед остановкой
            # ═══════════════════════════════════════════════════════════════
            operating_mode = self._get_operating_mode()
            
            # Проверить был ли Auto Sync активен
            auto_sync_was_active = (
                self._market_open_iterations > 0 or 
                self._market_closed_iterations > 0 or
                (operating_mode == 'simulation' and self._sync_task is not None)
            )
            
            if auto_sync_was_active:
                # Auto Sync был активен — отправить Stopped
                self._send_telegram_sync_status(operating_mode, 'auto', 'stopped')
                logger.info("[AUTO SYNC] Telegram: Auto Sync Stopped sent")
            
            # Обнулить флаги-счётчики
            self._market_open_iterations = 0
            self._market_closed_iterations = 0
            
            if self._sync_task:
                self.scheduler.cancel(self._sync_task)
                self._sync_task = None
            
            if self.scheduler and self.scheduler.is_running():
                self.scheduler.stop()
            
            # Сбросить флаги
            self._auto_sync_first_logged = False
            
            # Сбросить next_sync_time (чтобы UI показывал --)
            settings = self._load_sync_settings()
            settings['next_sync_time'] = None
            self._save_sync_settings(settings)
            
            # Сохранить состояние в файл
            _save_auto_sync_state(running=False)
            
            # Разрешить компьютеру засыпать
            _allow_sleep()
            
            logger.info("Auto Sync stopped")
            
        except Exception as e:
            logger.exception(f"Error stopping Auto Sync: {e}")
    
    def is_auto_sync_running(self) -> bool:
        """
        [DEPRECATED] Проверить работает ли Auto Sync (фоновый поток).
        
        ⚠️ Этот метод устарел! Используйте worker_client вместо него.
        
        Новый способ:
            from app.core.worker_client import is_worker_running
            is_worker_running()
        """
        return (
            self.scheduler is not None 
            and self.scheduler.is_running() 
            and self._sync_task is not None 
            and not self._sync_task.cancelled
        )
    
    @staticmethod
    def _send_delta_notification(
        client_name: str,
        deltas: Dict[str, int],
        prices: Dict[str, float],
        changes: List[dict]
    ):
        """Отправить уведомление об изменении дельты в Telegram"""
        try:
            from app.core.delta_tracker import DeltaTracker
            from app.core.telegram_service import get_telegram_service
            
            # Форматировать сообщение
            message = DeltaTracker.format_delta_message(
                client_name=client_name,
                deltas=deltas,
                prices=prices,
                changes=changes
            )
            
            # Отправить в Telegram
            telegram = get_telegram_service()
            telegram.send_message_async(message)
            logger.info(f"[MONITOR] Delta notification sent for {client_name}")
            
        except Exception as e:
            logger.error(f"[MONITOR] Failed to send delta notification: {e}")

    @staticmethod
    def _send_telegram_positions_synced(
            results: Dict[str, Any],
            operating_mode: str,
            sync_type: str
    ):
        """
        Отправить Telegram уведомление о синхронизации позиций.
        
        Отправляет только если были ордера (дельта > 0 → 0).
        """
        try:
            from app.core.telegram_service import get_telegram_service
            from app.core.cache_manager import get_cache, get_simulation_cache
            from app.core.config_cache import ConfigCache
            
            logger.debug(f"[TELEGRAM] _send_telegram_positions_synced called: mode={operating_mode}, type={sync_type}")
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                logger.debug("[TELEGRAM] Telegram is disabled, skipping")
                return
            
            logger.debug(f"[TELEGRAM] Results: {results}")
            
            # Проверить были ли ордера
            total_orders = 0
            clients_with_orders = []
            
            for client_id, client_result in results.items():
                if not isinstance(client_result, dict):
                    logger.debug(f"[TELEGRAM] Skipping {client_id}: not a dict")
                    continue
                if client_result.get('status') != 'success':
                    logger.debug(f"[TELEGRAM] Skipping {client_id}: status={client_result.get('status')}")
                    continue
                
                result = client_result.get('result', {})
                orders_count = result.get('summary', {}).get('orders_placed', 0)
                
                logger.debug(f"[TELEGRAM] Client {client_id}: orders_count={orders_count}")
                
                if orders_count > 0:
                    total_orders += orders_count
                    clients_with_orders.append({
                        'client_id': client_id,
                        'result': result,
                        'orders_count': orders_count
                    })
            
            # Если не было ордеров - не отправлять
            if total_orders == 0:
                logger.info("[TELEGRAM] No orders placed, skipping notification")
                return
            
            logger.info(f"[TELEGRAM] Sending notification: {total_orders} orders, {len(clients_with_orders)} clients")
            
            # ═══════════════════════════════════════════════════════════════
            # Main Account - ВСЕГДА из обычного кэша
            # ═══════════════════════════════════════════════════════════════
            cache = get_cache()
            main_account = cache.get('main_account', {})
            
            # Собрать позиции Main Account
            main_positions = []
            main_positions_value = 0.0
            
            for pos in main_account.get('positions', []):
                symbol = pos.get('symbol', '')
                qty = pos.get('quantity', 0)
                price = pos.get('price', 0)
                value = qty * price
                main_positions_value += value
                
                main_positions.append({
                    'symbol': symbol,
                    'action': 'BUY' if qty > 0 else 'SELL',
                    'quantity': abs(qty),
                    'price': price,
                    'value': value
                })
            
            # Total Value = liquidation_value (полная стоимость счёта)
            main_total = main_account.get('balances', {}).get('liquidation_value', 0)
            if main_total == 0:
                main_total = main_positions_value  # fallback
            
            # ═══════════════════════════════════════════════════════════════
            # Clients - из dry cache для SIMULATION, иначе из обычного кэша
            # ═══════════════════════════════════════════════════════════════
            if operating_mode == 'simulation':
                dry_cache = get_simulation_cache()
                clients_cache = dry_cache.get('clients', {})
            else:
                clients_cache = cache.get('clients', {})
            
            logger.debug(f"[TELEGRAM] clients_cache keys: {list(clients_cache.keys())}")
            
            # Получить имена клиентов из clients.json
            clients_config = ConfigCache.get_clients()
            logger.debug(f"[TELEGRAM] clients_config type: {type(clients_config)}")
            
            # Извлечь имена из slave_accounts
            client_names = {}
            if isinstance(clients_config, dict):
                # Структура: {"main_account": {...}, "slave_accounts": [{...}]}
                slave_accounts = clients_config.get('slave_accounts', [])
                for acc in slave_accounts:
                    if isinstance(acc, dict):
                        cid = acc.get('id', '')
                        client_names[cid] = acc.get('name', cid)
            elif isinstance(clients_config, list):
                # Если вдруг список
                for c in clients_config:
                    if isinstance(c, dict):
                        cid = c.get('id', '')
                        client_names[cid] = c.get('name', cid)
            
            logger.debug(f"[TELEGRAM] client_names: {client_names}")
            
            # Собрать данные клиентов
            clients_data = []
            
            for client_info in clients_with_orders:
                client_id = client_info['client_id']
                orders_count = client_info['orders_count']
                
                # Получить имя клиента из clients.json
                client_name = client_names.get(client_id, client_id)
                
                # Получить позиции клиента из кэша
                client_cache = clients_cache.get(client_id, {})
                
                # Собрать позиции клиента
                positions = []
                client_positions_value = 0.0
                
                for pos in client_cache.get('positions', []):
                    symbol = pos.get('symbol', '')
                    qty = pos.get('quantity', 0)
                    price = pos.get('price', 0)
                    value = qty * price
                    client_positions_value += value
                    
                    positions.append({
                        'symbol': symbol,
                        'action': 'BUY' if qty > 0 else 'SELL',
                        'quantity': abs(qty),
                        'price': price,
                        'value': value
                    })
                
                # Total Value = liquidation_value (полная стоимость счёта)
                client_total = client_cache.get('balances', {}).get('liquidation_value', 0)
                if client_total == 0:
                    client_total = client_positions_value  # fallback
                
                clients_data.append({
                    'name': client_name,
                    'positions': positions,
                    'positions_value': client_positions_value,
                    'total': client_total,
                    'orders_count': orders_count
                })
            
            # ═══════════════════════════════════════════════════════════════
            # Сообщение 1: notify_sync_status (completed)
            # ═══════════════════════════════════════════════════════════════
            sync_type_param = 'auto' if sync_type == "Auto Sync" else 'manual'
            telegram.notify_sync_status(
                operating_mode=operating_mode,
                sync_type=sync_type_param,
                action='completed'
            )
            
            # ═══════════════════════════════════════════════════════════════
            # Сообщение 2: notify_positions_synced (детали ордеров)
            # ═══════════════════════════════════════════════════════════════
            telegram.notify_positions_synced(
                main_positions=main_positions,
                main_positions_value=main_positions_value,
                main_total=main_total,
                clients_data=clients_data
            )
            
            logger.info(f"[TELEGRAM] Positions synced notification sent: {total_orders} orders")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send positions synced notification: {e}")


# ════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР (сингл-тон на уровне процесса)
# ════════════════════════════════════════════════════════════════

# Глобальный экземпляр (один на весь процесс Python)
_global_sync_service: Optional[SyncService] = None
_global_sync_service_lock = threading.Lock()


def get_sync_service() -> SyncService:
    """
    Получить глобальный экземпляр SyncService.
    
    ВАЖНО: Используем глобальную переменную, а не session_state,
    чтобы все сессии браузера работали с одним и тем же scheduler.
    """
    global _global_sync_service
    
    with _global_sync_service_lock:
        if _global_sync_service is None:
            # Получаем client_manager из session_state (если есть)
            client_manager = None
            if hasattr(st, 'session_state') and 'client_manager' in st.session_state:
                client_manager = st.session_state.client_manager
            _global_sync_service = SyncService(client_manager=client_manager)
        
        # Обновить client_manager если он ещё не установлен
        if hasattr(st, 'session_state') and 'client_manager' in st.session_state:
            _global_sync_service.set_client_manager(st.session_state.client_manager)
    
    return _global_sync_service
