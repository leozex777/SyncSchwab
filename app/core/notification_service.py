
# notification_service.py
# app.core.notification_service

"""
Сервис уведомлений для показа Toast в GUI.

Проблема: st.toast() работает только в главном потоке Streamlit,
а sync_service работает в фоновом потоке.

Решение: Уведомления сохраняются в очередь (JSON файл),
GUI читает очередь и показывает toast через st.fragment.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from app.core.logger import logger


class NotificationType(Enum):
    """Типы уведомлений"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Notification:
    """Структура уведомления"""
    type: str
    message: str
    timestamp: str = None
    symbol: Optional[str] = None
    details: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Notification':
        return cls(**data)


class NotificationService:
    """Сервис уведомлений"""
    
    QUEUE_FILE = Path("data/notifications_queue.json")
    MAX_QUEUE_SIZE = 50  # Максимум уведомлений в очереди
    
    def __init__(self):
        self.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_queue(self) -> List[dict]:
        """Загрузить очередь уведомлений"""
        try:
            if self.QUEUE_FILE.exists():
                with open(self.QUEUE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load notifications queue: {e}")
        return []
    
    def _save_queue(self, queue: List[dict]):
        """Сохранить очередь уведомлений"""
        try:
            with open(self.QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Failed to save notifications queue: {e}")
    
    def add(self, notification: Notification):
        """Добавить уведомление в очередь"""
        queue = self._load_queue()
        queue.append(notification.to_dict())
        
        # Ограничить размер очереди
        if len(queue) > self.MAX_QUEUE_SIZE:
            queue = queue[-self.MAX_QUEUE_SIZE:]
        
        self._save_queue(queue)
        logger.debug(f"Notification added: {notification.type} - {notification.message}")
    
    def get_pending(self, limit: int = 10) -> List[Notification]:
        """
        Получить и удалить pending уведомления.
        
        Returns:
            Список уведомлений для показа
        """
        queue = self._load_queue()
        
        if not queue:
            return []
        
        # Взять первые N уведомлений
        pending = queue[:limit]
        remaining = queue[limit:]
        
        # Сохранить оставшиеся
        self._save_queue(remaining)
        
        return [Notification.from_dict(n) for n in pending]
    
    def clear(self):
        """Очистить очередь"""
        self._save_queue([])
    
    # ════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ════════════════════════════════════════════════════════════════
    
    def success(self, message: str, symbol: str = None):
        """Добавить SUCCESS уведомление"""
        self.add(Notification(
            type=NotificationType.SUCCESS.value,
            message=message,
            symbol=symbol
        ))
    
    def error(self, message: str, symbol: str = None, details: str = None):
        """Добавить ERROR уведомление"""
        self.add(Notification(
            type=NotificationType.ERROR.value,
            message=message,
            symbol=symbol,
            details=details
        ))
    
    def warning(self, message: str, symbol: str = None):
        """Добавить WARNING уведомление"""
        self.add(Notification(
            type=NotificationType.WARNING.value,
            message=message,
            symbol=symbol
        ))
    
    def info(self, message: str):
        """Добавить INFO уведомление"""
        self.add(Notification(
            type=NotificationType.INFO.value,
            message=message
        ))
    
    # ════════════════════════════════════════════════════════════════
    # SYNC-SPECIFIC NOTIFICATIONS
    # ════════════════════════════════════════════════════════════════
    
    def sync_started(self, client_count: int, mode: str):
        """Уведомление о начале синхронизации"""
        self.info(f"🔄 Sync started: {client_count} clients ({mode})")
    
    def sync_completed(self, success_count: int, error_count: int):
        """Уведомление о завершении синхронизации"""
        if error_count == 0:
            self.success(f"✅ Sync completed: {success_count} orders successful")
        else:
            self.warning(f"⚠️ Sync completed: {success_count} success, {error_count} errors")
    
    def order_success(self, symbol: str, action: str, quantity: int):
        """Уведомление об успешном ордере"""
        self.success(f"✅ {action} {quantity} {symbol}", symbol=symbol)
    
    def order_error(self, symbol: str, action: str, error: str):
        """Уведомление об ошибке ордера"""
        self.error(f"❌ {action} {symbol}: {error}", symbol=symbol, details=error)
    
    def order_retry(self, symbol: str, attempt: int, max_attempts: int):
        """Уведомление о retry"""
        self.warning(f"⚠️ Retry {attempt}/{max_attempts} for {symbol}", symbol=symbol)
    
    def critical_error(self, message: str):
        """Уведомление о критической ошибке"""
        self.error(f"🛑 CRITICAL: {message}")


# ════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ════════════════════════════════════════════════════════════════

_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Получить глобальный экземпляр NotificationService"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


# ════════════════════════════════════════════════════════════════
# STREAMLIT INTEGRATION
# ════════════════════════════════════════════════════════════════

def show_pending_toasts():
    """
    Показать pending уведомления как toast.
    Вызывать из GUI (например в st.fragment).
    
    Usage:
        import streamlit as st
        from app.core.notification_service import show_pending_toasts
        
        @st.fragment(run_every=2)
        def notification_fragment():
            show_pending_toasts()
    """
    import streamlit as st
    
    service = get_notification_service()
    notifications = service.get_pending(limit=5)
    
    for notif in notifications:
        icon = {
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️'
        }.get(notif.type, 'ℹ️')
        
        st.toast(f"{icon} {notif.message}")
