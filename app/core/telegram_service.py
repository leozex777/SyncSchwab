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
from datetime import datetime, timedelta

from app.core.logger import logger
from app.core.json_utils import load_json, save_json
from pathlib import Path


# ════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ════════════════════════════════════════════════════════════════

GENERAL_SETTINGS_FILE = Path("config/general_settings.json")
TELEGRAM_NOTIFICATIONS_FILE = Path("config/telegram_notifications.json")
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT = 10  # секунд

# Настройки уведомлений по умолчанию
TELEGRAM_NOTIFICATIONS_DEFAULTS = {
    "market": {
        "opened": True,
        "closed_until": True,
        "closed_summary": True
    },
    "sync": {
        "positions_synced": True
    }
}


# ════════════════════════════════════════════════════════════════
# TELEGRAM SERVICE
# ════════════════════════════════════════════════════════════════

class TelegramService:
    """Сервис для отправки Telegram уведомлений"""
    
    def __init__(self):
        self._lock = threading.Lock()
        # Создать файл настроек если не существует
        self._ensure_notifications_file()

    @staticmethod
    def _ensure_notifications_file():
        """Создать файл настроек уведомлений если не существует"""
        if not TELEGRAM_NOTIFICATIONS_FILE.exists():
            TELEGRAM_NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            save_json(str(TELEGRAM_NOTIFICATIONS_FILE), TELEGRAM_NOTIFICATIONS_DEFAULTS)
            logger.info(f"[TELEGRAM] Created default notifications config: {TELEGRAM_NOTIFICATIONS_FILE}")

    @staticmethod
    def _is_notification_enabled(group: str, key: str) -> bool:
        """
        Проверить включена ли функция уведомления.
        
        Args:
            group: Группа ('market', 'sync')
            key: Ключ ('opened', 'positions_synced', ...)
        
        Returns:
            True если включена, False если выключена
        """
        try:
            settings = load_json(str(TELEGRAM_NOTIFICATIONS_FILE), default=TELEGRAM_NOTIFICATIONS_DEFAULTS)
            return settings.get(group, {}).get(key, True)
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to check notification setting: {e}")
            return True  # По умолчанию включено

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
    # УНИВЕРСАЛЬНОЕ УВЕДОМЛЕНИЕ О СТАТУСЕ SYNC
    # ════════════════════════════════════════════════════════════════
    
    def notify_sync_status(
        self,
        operating_mode: str,
        sync_type: str,
        action: str = None
    ):
        """
        Универсальное уведомление о статусе синхронизации.
        
        Args:
            operating_mode: 'live', 'simulation', 'monitor_live', 'monitor_simulation'
            sync_type: 'auto' или 'manual'
            action: 'started', 'stopped', 'completed' или None (без действия)
        
        Примеры сообщений:
            С action:
                🔴 Live Mode: Auto Sync
                ▶️ Started
                ⏰ Friday, 10.01.2026, 14:32 ET
            
            Без action (action=None):
                🔴 Live Mode: Sync
                ⏰ Friday, 10.01.2026, 14:32 ET
        """
        import pytz
        
        # ═══════════════════════════════════════════════════════════════
        # Первая строка: Режим + Тип
        # ═══════════════════════════════════════════════════════════════
        if operating_mode == 'live':
            if sync_type == 'auto':
                mode_line = "🔴 <b>Live Mode</b>: Auto Sync"
            else:
                mode_line = "🔴 <b>Live Mode</b>: Sync"
        elif operating_mode == 'simulation':
            if sync_type == 'auto':
                mode_line = "🔶 <b>Simulation</b>: Auto Sync"
            else:
                mode_line = "🔶 <b>Simulation</b>: Sync"
        elif operating_mode == 'monitor_live':
            mode_line = "🔍🔴 <b>Monitor Live Delta</b>"
        elif operating_mode == 'monitor_simulation':
            mode_line = "🔍🔶 <b>Monitor Simulation Delta</b>"
        else:
            mode_line = f"❓ <b>{operating_mode}</b>"
        
        # ═══════════════════════════════════════════════════════════════
        # Вторая строка: Действие (опционально)
        # ═══════════════════════════════════════════════════════════════
        action_line = None
        if action:
            action_icons = {
                'started': '▶️ Started',
                'stopped': '⏹️ Stopped',
                'completed': '✅ Positions Synced'
            }
            action_line = action_icons.get(action.lower(), f'❓ {action}')
        
        # ═══════════════════════════════════════════════════════════════
        # Последняя строка: Время (Friday, 10.01.2026, 14:32 ET)
        # ═══════════════════════════════════════════════════════════════
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        timestamp = now_et.strftime('%A, %d.%m.%Y, %H:%M ET')
        
        # Собрать сообщение
        text = f"{mode_line}\n"
        if action_line:
            text += f"{action_line}\n"
        text += f"⏰ {timestamp}"
        
        self.send_message_async(text)
    
    # ════════════════════════════════════════════════════════════════
    # УВЕДОМЛЕНИЯ О СИНХРОНИЗАЦИИ ПОЗИЦИЙ
    # ════════════════════════════════════════════════════════════════
    
    def notify_positions_synced(
        self,
        main_positions: list,
        main_positions_value: float,
        main_total: float,
        clients_data: list
    ):
        """
        Уведомление о синхронизации позиций (детали ордеров).
        Функция общего назначения (настраиваемая).
        
        Отправляется ПОСЛЕ notify_sync_status(..., 'completed').
        
        Args:
            main_positions: [{'symbol': 'QLD', 'action': 'BUY', 'quantity': 180, 'price': 72.32, 'value': 13017.60},...]
            main_positions_value: Стоимость позиций Main Account (сумма qty × price)
            main_total: Полная стоимость Main Account (liquidation_value)
            clients_data: [{'name': 'Luba', 'positions': [...], 'positions_value': 9948.30, 'total': 9948.46,
            'orders_count': 2}, ...]
        """
        # Проверить включена ли функция
        if not self._is_notification_enabled('sync', 'positions_synced'):
            return
        
        # Main Account
        text = "📊 🏦 <b>Main Account</b>\n"
        for pos in main_positions:
            action = pos.get('action', 'BUY')
            qty = int(pos.get('quantity', 0))
            symbol = pos.get('symbol', '')
            price = pos.get('price', 0)
            value = pos.get('value', qty * price)
            text += f"   {action} {qty} {symbol} @ ${price:,.2f} = ${value:,.2f}\n"
        text += f"💰 Positions Value: ${main_positions_value:,.2f}\n"
        text += f"💰 Total Value: ${main_total:,.2f}\n"
        text += f"📈 Positions: {len(main_positions)}\n"
        
        # Clients
        for client in clients_data:
            name = client.get('name', 'Unknown')
            positions = client.get('positions', [])
            positions_value = client.get('positions_value', 0)
            total = client.get('total', 0)
            orders_count = client.get('orders_count', len(positions))
            
            text += f"📊 👥 <b>{name}</b> ✅\n"
            for pos in positions:
                action = pos.get('action', 'BUY')
                qty = int(pos.get('quantity', 0))
                symbol = pos.get('symbol', '')
                price = pos.get('price', 0)
                value = pos.get('value', qty * price)
                text += f"   {action} {qty} {symbol} @ ${price:,.2f} = ${value:,.2f}\n"
            text += f"💰 Positions Value: ${positions_value:,.2f}\n"
            text += f"💰 Total Value: ${total:,.2f}\n"
            text += f"📈 Orders: {orders_count}\n"
        
        self.send_message_async(text)
    
    def notify_market_closed_summary(
        self,
        main_total: float,
        main_pl: float,
        main_positions_value: float,
        clients_data: list
    ):
        """
        Итоги дня - данные аккаунтов.
        Функция общего назначения (настраиваемая).
        
        Отправляется ПЕРЕД notify_market_closed_until() при закрытии биржи.
        
        Args:
            main_total: Общая стоимость Main Account (liquidation_value)
            main_pl: P&L Main Account
            main_positions_value: Стоимость позиций Main Account
            clients_data: [{'name': 'Luba', 'total': 9948.46, 'positions_value': 9948.30, 'pl': -59.89}, ...]
        """
        # Проверить включена ли функция
        if not self._is_notification_enabled('market', 'closed_summary'):
            return
        
        # Main Account
        text = "📊 🏦 <b>Main Account</b>\n"
        if main_pl >= 0:
            text += f"   P&L: +${main_pl:,.2f}\n"
        else:
            text += f"   P&L: -${abs(main_pl):,.2f}\n"
        text += f"💰 Positions Value: ${main_positions_value:,.2f}\n"
        text += f"💰 Total Value: ${main_total:,.2f}\n"
        
        # Clients
        for client in clients_data:
            name = client.get('name', 'Unknown')
            total = client.get('total', 0)
            positions_value = client.get('positions_value', 0)
            pl = client.get('pl', 0)
            
            text += f"📊 👥 <b>{name}</b>\n"
            if pl >= 0:
                text += f"   P&L: +${pl:,.2f}\n"
            else:
                text += f"   P&L: -${abs(pl):,.2f}\n"
            text += f"💰 Positions Value: ${positions_value:,.2f}\n"
            text += f"💰 Total Value: ${total:,.2f}\n"
        
        self.send_message_async(text)
    
    def notify_market_closed_until(self, opens_at: str):
        """
        Уведомление о закрытии биржи с информацией о следующем открытии.
        Функция общего назначения (настраиваемая).
        
        Args:
            opens_at: Когда откроется (например "Friday, 10.01.2026, 09:30 ET")
        """
        # Проверить включена ли функция
        if not self._is_notification_enabled('market', 'closed_until'):
            return
        
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        timestamp = now_et.strftime('%A, %d.%m.%Y, %H:%M ET')
        
        text = f"🔒 <b>Market Closed.</b>\n"
        text += f"⏰ {timestamp}\n\n"
        text += f"🔔 <b>Opens:</b>\n"
        text += f"⏰ {opens_at}\n"
        text += "⏹️ Synchronization is stopped"
        
        self.send_message_async(text)
    
    def notify_market_opened(self):
        """
        Уведомление об открытии биржи.
        Функция общего назначения (настраиваемая).
        """
        # Проверить включена ли функция
        if not self._is_notification_enabled('market', 'opened'):
            return
        
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        timestamp = now_et.strftime('%A, %d.%m.%Y, %H:%M ET')
        
        text = f"🔔 <b>Market Opened</b>\n"
        text += f"⏰ {timestamp}\n"
        text += "▶️ Synchronization is started"
        
        self.send_message_async(text)


# ════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════

def get_next_market_open() -> tuple:
    """
    Определить когда следующий раз откроется биржа.
    
    Учитывает:
    - Выходные (Сб, Вс)
    - Праздники из market_calendar.json
    - Время открытия 09:30 ET
    
    Returns:
        tuple: (opens_at_str, reason)
        opens_at_str: "Monday, 13.01.2026, 09:30 ET"
        reason: "Weekend", "Holiday (MLK Day)", etc.
    """
    import pytz
    from app.core.json_utils import load_json
    
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    
    # Загрузить календарь
    calendar_file = Path("config/market_calendar.json")
    calendar = load_json(str(calendar_file), default={})
    holidays = {h['date']: h.get('name', 'Holiday') for h in calendar.get('holidays', [])}
    
    # Найти следующий рабочий день
    check_date = now_et
    reason = None
    
    # Определить текущую причину закрытия
    if now_et.weekday() == 5:
        reason = "Weekend (Saturday)"
    elif now_et.weekday() == 6:
        reason = "Weekend (Sunday)"
    elif now_et.strftime('%Y-%m-%d') in holidays:
        reason = f"Holiday ({holidays[now_et.strftime('%Y-%m-%d')]})"
    elif now_et.hour >= 16:
        reason = "After market close"
    elif now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30):
        reason = "Before market open"
    
    # Искать следующий рабочий день
    for _ in range(10):  # Максимум 10 дней вперёд
        # Если сейчас до 09:30 в рабочий день — откроется сегодня
        if check_date.date() == now_et.date():
            if now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30):
                # Сегодня до открытия
                if check_date.weekday() < 5 and check_date.strftime('%Y-%m-%d') not in holidays:
                    open_time = check_date.replace(hour=9, minute=30, second=0, microsecond=0)
                    opens_at_str = open_time.strftime('%A, %d.%m.%Y, %H:%M ET')
                    return opens_at_str, reason
        
        # Перейти на следующий день
        check_date = check_date + timedelta(days=1)
        check_date = check_date.replace(hour=9, minute=30, second=0, microsecond=0)
        
        date_str = check_date.strftime('%Y-%m-%d')
        
        # Проверить выходные
        if check_date.weekday() >= 5:
            continue
        
        # Проверить праздники
        if date_str in holidays:
            continue
        
        # Нашли рабочий день
        opens_at_str = check_date.strftime('%A, %d.%m.%Y, %H:%M ET')
        return opens_at_str, reason
    
    return "Unknown", reason


def get_market_closed_time() -> str:
    """
    Получить время закрытия биржи для текущего момента.
    
    Returns:
        str: "Friday, January 10, 16:00 ET"
    """
    import pytz
    
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    
    # Если после 16:00 — закрылась сегодня
    if now_et.hour >= 16:
        closed_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    # Если выходной — закрылась в пятницу
    elif now_et.weekday() == 5:  # Суббота
        days_back = 1
        closed_time = (now_et - timedelta(days=days_back)).replace(hour=16, minute=0, second=0, microsecond=0)
    elif now_et.weekday() == 6:  # Воскресенье
        days_back = 2
        closed_time = (now_et - timedelta(days=days_back)).replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        # До открытия в будний день — закрылась вчера
        closed_time = (now_et - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    
    return closed_time.strftime('%A, %B %d, %H:%M ET')


def get_market_opened_time() -> str:
    """
    Получить время открытия биржи для текущего момента.
    
    Returns:
        str: "Monday, January 6, 09:30 ET"
    """
    import pytz
    
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    
    opened_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    return opened_time.strftime('%A, %B %d, %H:%M ET')


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
