# telegram_service.py
# app.core.telegram_service

"""
Telegram Bot Service для отправки уведомлений.

Использует Telegram Bot API напрямую (без библиотек).
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import threading
from typing import Optional
from datetime import datetime

from app.core.logger import logger
from app.core.json_utils import load_json
from pathlib import Path


# ════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ════════════════════════════════════════════════════════════════

GENERAL_SETTINGS_FILE = Path("config/general_settings.json")
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT = 10  # секунд


# ════════════════════════════════════════════════════════════════
# TELEGRAM SERVICE
# ════════════════════════════════════════════════════════════════

class TelegramService:
    """Сервис для отправки Telegram уведомлений"""
    
    def __init__(self):
        self._lock = threading.Lock()

    @staticmethod
    def _get_settings() -> dict:
        """Получить настройки Telegram из general_settings.json"""
        try:
            settings = load_json(str(GENERAL_SETTINGS_FILE))
            return settings.get("notifications", {})
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to load settings: {e}")
            return {}
    
    def is_enabled(self) -> bool:
        """Проверить включен ли Telegram"""
        settings = self._get_settings()
        return settings.get("telegram_enabled", False)
    
    def _get_credentials(self) -> tuple:
        """Получить token и chat_id"""
        settings = self._get_settings()
        token = settings.get("telegram_bot_token", "")
        chat_id = settings.get("telegram_chat_id", "")
        return token, chat_id
    
    def _call_api(self, method: str, params: dict) -> dict:
        """
        Вызвать Telegram Bot API.
        
        Args:
            method: Метод API (sendMessage, getMe, etc.)
            params: Параметры запроса
            
        Returns:
            Ответ API как dict
        """
        token, _ = self._get_credentials()
        
        if not token:
            raise ValueError("Telegram bot token not configured")
        
        url = TELEGRAM_API_URL.format(token=token, method=method)
        data = urllib.parse.urlencode(params).encode('utf-8')
        
        request = urllib.request.Request(url, data=data, method='POST')
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error(f"[TELEGRAM] HTTP Error {e.code}: {error_body}")
            raise
        except urllib.error.URLError as e:
            logger.error(f"[TELEGRAM] URL Error: {e.reason}")
            raise
    
    def test_connection(self) -> tuple:
        """
        Проверить подключение к Telegram.
        
        Returns:
            (success: bool, message: str)
        """
        token, chat_id = self._get_credentials()
        
        if not token:
            return False, "Bot token not configured"
        
        if not chat_id:
            return False, "Chat ID not configured"
        
        try:
            # Проверить бота
            result = self._call_api("getMe", {})
            
            if not result.get("ok"):
                return False, f"Invalid bot token: {result.get('description', 'Unknown error')}"
            
            bot_name = result.get("result", {}).get("username", "Unknown")
            
            # Отправить тестовое сообщение
            test_result = self._call_api("sendMessage", {
                "chat_id": chat_id,
                "text": "🔗 SyncSchwab connected successfully!\n\nTelegram notifications are now enabled.",
                "parse_mode": "HTML"
            })
            
            if not test_result.get("ok"):
                return False, f"Failed to send message: {test_result.get('description', 'Unknown error')}"
            
            return True, f"Connected to @{bot_name}"
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid bot token"
            elif e.code == 400:
                return False, "Invalid chat ID"
            else:
                return False, f"HTTP Error: {e.code}"
        except urllib.error.URLError as e:
            return False, f"Network error: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Отправить сообщение в Telegram.
        
        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
            
        Returns:
            True если успешно
        """
        if not self.is_enabled():
            return False
        
        token, chat_id = self._get_credentials()
        
        if not token or not chat_id:
            logger.warning("[TELEGRAM] Bot token or chat ID not configured")
            return False
        
        try:
            with self._lock:
                result = self._call_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                })
            
            if result.get("ok"):
                logger.debug(f"[TELEGRAM] Message sent successfully")
                return True
            else:
                logger.error(f"[TELEGRAM] Failed to send: {result.get('description')}")
                return False
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Error sending message: {e}")
            return False
    
    def send_message_async(self, text: str, parse_mode: str = "HTML"):
        """
        Отправить сообщение асинхронно (в отдельном потоке).
        Не блокирует основной поток.
        """
        if not self.is_enabled():
            return
        
        thread = threading.Thread(
            target=self.send_message,
            args=(text, parse_mode),
            daemon=True
        )
        thread.start()
    
    # ════════════════════════════════════════════════════════════════
    # ФОРМАТИРОВАННЫЕ СООБЩЕНИЯ
    # ════════════════════════════════════════════════════════════════
    
    def notify_auto_sync_started(self, interval: str, mode: str):
        """Уведомление о запуске Auto Sync"""
        emoji = "🔴" if mode == "LIVE" else "🔶"
        text = (
            f"🚀 <b>Auto Sync Started</b>\n\n"
            f"📊 Mode: {emoji} {mode}\n"
            f"⏱ Interval: {interval}\n"
            f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message_async(text)
    
    def notify_auto_sync_stopped(self):
        """Уведомление об остановке Auto Sync"""
        text = (
            f"⏹ <b>Auto Sync Stopped</b>\n\n"
            f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message_async(text)
    
    def notify_sync_completed(
        self,
        mode: str,
        clients_count: int,
        orders_count: int,
        errors_count: int = 0
    ):
        """Уведомление о завершении синхронизации"""
        emoji = "🔴" if mode == "LIVE" else "🔶"
        status = "✅" if errors_count == 0 else "⚠️"
        
        text = (
            f"{status} <b>Sync Completed</b>\n\n"
            f"📊 Mode: {emoji} {mode}\n"
            f"👥 Clients: {clients_count}\n"
            f"📝 Orders: {orders_count}\n"
        )
        
        if errors_count > 0:
            text += f"❌ Errors: {errors_count}\n"
        
        text += f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        
        self.send_message_async(text)
    
    def notify_order_executed(
        self,
        client_name: str,
        symbol: str,
        action: str,
        quantity: int,
        price: float = None
    ):
        """Уведомление о выполненном ордере (только для LIVE)"""
        emoji = "🟢" if action == "BUY" else "🔴"
        
        text = (
            f"{emoji} <b>Order Executed</b>\n\n"
            f"👤 Client: {client_name}\n"
            f"📈 {action} {quantity} {symbol}\n"
        )
        
        if price:
            text += f"💰 Price: ${price:.2f}\n"
        
        text += f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        
        self.send_message_async(text)
    
    def notify_order_error(
        self,
        client_name: str,
        symbol: str,
        action: str,
        error: str
    ):
        """Уведомление об ошибке ордера"""
        text = (
            f"❌ <b>Order Failed</b>\n\n"
            f"👤 Client: {client_name}\n"
            f"📈 {action} {symbol}\n"
            f"⚠️ Error: {error}\n"
            f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message_async(text)
    
    def notify_error(self, error_message: str):
        """Уведомление об общей ошибке"""
        text = (
            f"🛑 <b>Error</b>\n\n"
            f"⚠️ {error_message}\n"
            f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message_async(text)
    
    def notify_market_closed(self):
        """Уведомление, что рынок закрыт"""
        text = (
            f"🔒 <b>Market Closed</b>\n\n"
            f"Auto Sync skipped - market is closed.\n"
            f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message_async(text)


# ════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ════════════════════════════════════════════════════════════════

_telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> TelegramService:
    """Получить глобальный экземпляр TelegramService"""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service
