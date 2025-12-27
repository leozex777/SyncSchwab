
# sync_service.py
# app.core.sync_service

import streamlit as st
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core.logger import logger
from app.core.scheduler import EventScheduler
from app.core.json_utils import load_json, save_json
from pathlib import Path


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
        """Получить operating_mode из general_settings.json"""
        settings = load_json("config/general_settings.json", default={})
        return settings.get('operating_mode', 'dry_run')

    @staticmethod
    def is_dry_run_mode() -> bool:
        """Проверить находимся ли в режиме DRY RUN"""
        return SyncService._get_operating_mode() != 'live'
    
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
        client_manager = st.session_state.client_manager
        
        if settings.get('sync_all_enabled', True):
            return [c.id for c in client_manager.get_enabled_clients()]
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
        mode_icons = {
            'dry_run': "DRY RUN 🧪",
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

            # Импортировать MultiSynchronizer
            from app.models.copier.multi_sync import MultiSynchronizer

            # Определить skip_history
            # DRY RUN / SIMULATION + Auto Sync + не первый запуск = пропустить запись
            skip_history = False
            if operating_mode != 'live' and source == "auto":
                if self._auto_sync_first_logged:
                    skip_history = True
                    logger.info(f"📝 {mode_str} Auto Sync: skipping history (not first run)")
                else:
                    # Первый запуск — записать и установить флаг
                    self._auto_sync_first_logged = True
                    logger.info(f"📝 {mode_str} Auto Sync: writing history (first run)")

            # Создать synchronizer (режим определяется автоматически из настроек)
            multi_sync = MultiSynchronizer(
                main_client=main_client,
                client_manager=client_manager,
                operating_mode=None  # None = читать из general_settings.json
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
    
    # ════════════════════════════════════════════════════════════════
    # AUTO SYNC (с планировщиком)
    # ════════════════════════════════════════════════════════════════
    
    def _auto_sync_task(self):
        """Задача для периодической синхронизации"""
        logger.info("Auto sync task triggered")
        client_ids = self.get_auto_sync_clients()
        self._perform_sync(client_ids, source="auto")
    
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
            
            # Логировать режим
            operating_mode = self._get_operating_mode()
            mode_icons = {
                'dry_run': "DRY RUN 🧪",
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


# ════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ════════════════════════════════════════════════════════════════

def get_sync_service() -> SyncService:
    """Получить глобальный экземпляр SyncService"""
    if 'sync_service' not in st.session_state:
        # Передаем client_manager при создании
        client_manager = st.session_state.get('client_manager')
        st.session_state.sync_service = SyncService(client_manager=client_manager)
    return st.session_state.sync_service
