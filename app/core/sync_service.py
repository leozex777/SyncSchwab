
# sync_service.py
# app.core.sync_service

import os
import threading
import streamlit as st
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core.logger import logger
from app.core.scheduler import EventScheduler
from app.core.json_utils import load_json, save_json
from app.core.config_cache import ConfigCache
from pathlib import Path


# ════════════════════════════════════════════════════════════════
# ФАЙЛ СОСТОЯНИЯ AUTO SYNC (для восстановления после перезагрузки браузера)
# ════════════════════════════════════════════════════════════════

AUTO_SYNC_STATE_FILE = Path("config/auto_sync_state.json")
PENDING_MANUAL_SYNC_FLAG = Path("config/pending_manual_sync.flag")


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


def is_auto_sync_running_from_file() -> bool:
    """
    Проверить работает ли Auto Sync (из файла).
    Используется для восстановления состояния при перезагрузке браузера.
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
            # Другой PID — процесс мог умереть или это старый файл
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
        """Загрузить настройки"""
        return load_json(str(SyncService._get_sync_settings_file()), default=self._get_sync_defaults())
    
    def _save_sync_settings(self, settings: dict):
        """Сохранить настройки"""
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
        """Получить operating_mode из general_settings.json (через кэш)"""
        settings = ConfigCache.get_general_settings()
        return settings.get('operating_mode', 'monitor')

    @staticmethod
    def _get_monitor_sync_mode() -> str:
        """Получить monitor_sync_mode из general_settings.json (через кэш)"""
        settings = ConfigCache.get_general_settings()
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
            return market_open <= now <= market_close
        else:
            # Custom hours
            start_str = settings.get('auto_sync_start_time', '09:30')
            end_str = settings.get('auto_sync_end_time', '16:00')
            
            try:
                now = datetime.now()
                start_time = datetime.strptime(start_str, "%H:%M").time()
                end_time = datetime.strptime(end_str, "%H:%M").time()
                
                return start_time <= now.time() <= end_time
            except (ValueError, TypeError):
                return True
    
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
        """Обновить статус после синхронизации"""
        settings = self._load_sync_settings()
        
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        # Обновить время последней синхронизации
        settings['last_sync_time'] = now.isoformat()
        
        # Обновить счетчик за день
        if settings.get('syncs_today_date') != today_str:
            settings['syncs_today'] = 1
            settings['syncs_today_date'] = today_str
        else:
            settings['syncs_today'] = settings.get('syncs_today', 0) + 1
        
        self._save_sync_settings(settings)
        logger.info(f"Sync status updated: syncs_today={settings['syncs_today']}")
    
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
            'monitor': f"MONITOR 🔍 ({monitor_sync_mode.upper()})",
            'simulation': "SIMULATION 🔶",
            'live': "LIVE 🔴"
        }
        mode_str = mode_icons.get(operating_mode, "UNKNOWN")
        
        logger.info(f"Starting {source} sync for {len(client_ids)} clients ({mode_str})")

        # Проверить Active Hours для Auto Sync (только в LIVE режиме)
        if source == "auto" and operating_mode == 'live' and not self.is_within_active_hours():
            logger.info("Outside active hours, skipping sync")
            return {"status": "skipped", "reason": "outside_active_hours"}
        
        # В DRY RUN / SIMULATION логировать что проверка пропущена
        if source == "auto" and operating_mode != 'live' and not self.is_within_active_hours():
            logger.info(f"{mode_str}: Outside active hours, but continuing for testing")

        if not client_ids:
            logger.warning("No clients to sync")
            return {"status": "skipped", "reason": "no_clients"}

        try:
            # Получить main client
            from app.core.config import get_main_client
            main_client = get_main_client()

            if not main_client:
                logger.error("Main account not authorized")
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
                        logger.error(f"[MONITOR] Error tracking {client_id}: {e}")
                        results[client_id] = {'status': 'error', 'error': str(e)}
                
                logger.info(f"[MONITOR] Delta tracking completed: {len(results)} clients")
                return results

            # ════════════════════════════════════════════════════════════════
            # ОБЫЧНЫЙ SYNC (Simulation, Live, или Monitor Manual)
            # ════════════════════════════════════════════════════════════════

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

            return results

        except Exception as e:
            logger.exception(f"Sync error: {e}")
            return {"status": "error", "reason": str(e)}
    
    # ════════════════════════════════════════════════════════════════
    # MANUAL SYNC
    # ════════════════════════════════════════════════════════════════
    
    def run_manual_sync(self) -> Dict[str, Any]:
        """Запустить Manual Sync (однократно)"""
        client_ids = self.get_manual_sync_clients()
        return self._perform_sync(client_ids, source="manual")
    
    def execute_apply_now(self) -> Dict[str, Any]:
        """
        Выполнить Apply немедленно.
        
        Использует блокировку чтобы дождаться завершения текущего sync.
        
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
    # AUTO SYNC (с планировщиком)
    # ════════════════════════════════════════════════════════════════
    
    def _auto_sync_task(self):
        """Задача для периодической синхронизации"""
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
                
                client_ids = self.get_auto_sync_clients()
                self._perform_sync(client_ids, source="auto")
                
                # Проверить pending_manual_sync ПОСЛЕ (если был установлен во время sync)
                if self._check_pending_manual_sync():
                    self._clear_pending_manual_sync()
                    logger.info("[PENDING] Executing queued manual sync (after auto)")
                    self.run_manual_sync()
            finally:
                self._sync_in_progress = False

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
        """Запустить Auto Sync"""
        try:
            # Сбросить флаг первого запуска DRY RUN (новая сессия)
            self._auto_sync_first_logged = False
            
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
            
            # Запланировать периодическую задачу
            # Первый запуск сразу (delay_first=0)
            self._sync_task = self.scheduler.schedule_every(
                interval=interval_sec,
                func=self._auto_sync_task,
                delay_first=0,  # Запустить сразу
                name="auto_sync"
            )
            
            # Сохранить состояние в файл (для восстановления после перезагрузки браузера)
            _save_auto_sync_state(running=True, interval=interval_str)
            
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
            return True
            
        except Exception as e:
            logger.exception(f"Failed to start Auto Sync: {e}")
            return False
    
    def stop_auto_sync(self):
        """Остановить Auto Sync"""
        try:
            if self._sync_task:
                self.scheduler.cancel(self._sync_task)
                self._sync_task = None
            
            if self.scheduler and self.scheduler.is_running():
                self.scheduler.stop()
            
            # Сбросить флаг первого запуска DRY RUN
            self._auto_sync_first_logged = False
            
            # Сохранить состояние в файл
            _save_auto_sync_state(running=False)
            
            logger.info("Auto Sync stopped")
            
        except Exception as e:
            logger.exception(f"Error stopping Auto Sync: {e}")
    
    def is_auto_sync_running(self) -> bool:
        """Проверить работает ли Auto Sync"""
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
