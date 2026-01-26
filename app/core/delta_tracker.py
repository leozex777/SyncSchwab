# delta_tracker.py
# app.core.delta_tracker

"""
Трекер изменений дельты для режима Monitor.

Функции:
- Хранение последней известной дельты для каждого клиента
- Сравнение текущей дельты с предыдущей
- Запись изменений в delta history (JSON файл, 1 год хранения)
- Отправка уведомлений в Telegram при изменениях
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from app.core.logger import logger
from app.core.json_utils import load_json, save_json


# ════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════

DELTA_HISTORY_DIR = Path("data/clients")
DELTA_RETENTION_DAYS = 365  # Хранить историю 1 год


# ════════════════════════════════════════════════════════════════
# СТРУКТУРЫ ДАННЫХ
# ════════════════════════════════════════════════════════════════

class DeltaSnapshot:
    """Снимок дельты в определённый момент"""
    
    def __init__(
        self,
        timestamp: str,
        deltas: Dict[str, int],  # {symbol: quantity}
        prices: Dict[str, float],  # {symbol: price}
        total_estimated: float = 0.0,
        change_reason: str = "initial"
    ):
        self.timestamp = timestamp
        self.deltas = deltas
        self.prices = prices
        self.total_estimated = total_estimated
        self.change_reason = change_reason
    
    def to_dict(self) -> dict:
        """Конвертировать в словарь для JSON"""
        items = []
        for symbol, quantity in self.deltas.items():
            price = self.prices.get(symbol, 0)
            action = "BUY" if quantity > 0 else "SELL"
            items.append({
                "symbol": symbol,
                "action": action,
                "quantity": abs(quantity),
                "price": price,
                "estimated_cost": abs(quantity) * price
            })
        
        return {
            "timestamp": self.timestamp,
            "deltas": items,
            "total_estimated": self.total_estimated,
            "change_reason": self.change_reason
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DeltaSnapshot':
        """Создать из словаря"""
        deltas = {}
        prices = {}
        for item in data.get("deltas", []):
            symbol = item["symbol"]
            quantity = item["quantity"]
            if item["action"] == "SELL":
                quantity = -quantity
            deltas[symbol] = quantity
            prices[symbol] = item.get("price", 0)
        
        return cls(
            timestamp=data.get("timestamp", ""),
            deltas=deltas,
            prices=prices,
            total_estimated=data.get("total_estimated", 0),
            change_reason=data.get("change_reason", "unknown")
        )


# ════════════════════════════════════════════════════════════════
# DELTA TRACKER
# ════════════════════════════════════════════════════════════════

class DeltaTracker:
    """Трекер изменений дельты"""
    
    def __init__(self):
        # Кэш последних дельт для каждого клиента (в памяти)
        self._last_deltas: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _get_history_file(client_id: str) -> Path:
        """Путь к файлу истории дельт"""
        DELTA_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        return DELTA_HISTORY_DIR / f"{client_id}_history_delta.json"
    
    def _load_history(self, client_id: str) -> List[dict]:
        """Загрузить историю дельт клиента"""
        file_path = self._get_history_file(client_id)
        data = load_json(str(file_path), default={"client_id": client_id, "history": []})
        return data.get("history", [])
    
    def _save_history(self, client_id: str, history: List[dict]):
        """Сохранить историю дельт клиента"""
        file_path = self._get_history_file(client_id)
        
        # Очистить старые записи (старше 1 года)
        cutoff = datetime.now() - timedelta(days=DELTA_RETENTION_DAYS)
        history = [
            h for h in history
            if datetime.fromisoformat(h.get("timestamp", "2000-01-01")) > cutoff
        ]
        
        data = {
            "client_id": client_id,
            "history": history
        }
        save_json(str(file_path), data)
    
    def get_last_delta(self, client_id: str) -> Optional[Dict[str, int]]:
        """Получить последнюю известную дельту для клиента"""
        # Сначала проверить кэш в памяти
        if client_id in self._last_deltas:
            return self._last_deltas[client_id]
        
        # Загрузить из файла
        history = self._load_history(client_id)
        if history:
            last_snapshot = DeltaSnapshot.from_dict(history[-1])
            self._last_deltas[client_id] = last_snapshot.deltas
            return last_snapshot.deltas
        
        return None

    @staticmethod
    def compare_deltas(
        old_deltas: Optional[Dict[str, int]],
        new_deltas: Dict[str, int]
    ) -> Tuple[bool, str, List[dict]]:
        """
        Сравнить две дельты.
        
        Returns:
            (changed: bool, reason: str, changes: List[dict])
        """
        if old_deltas is None:
            return True, "initial", []
        
        changes = []
        changed = False
        
        # Проверить все символы в new_deltas
        all_symbols = set(old_deltas.keys()) | set(new_deltas.keys())
        
        for symbol in all_symbols:
            old_qty = old_deltas.get(symbol, 0)
            new_qty = new_deltas.get(symbol, 0)
            
            if old_qty != new_qty:
                changed = True
                diff = new_qty - old_qty
                
                if old_qty == 0 and new_qty != 0:
                    change_type = "new_symbol"
                elif new_qty == 0 and old_qty != 0:
                    change_type = "symbol_removed"
                else:
                    change_type = "quantity_changed"
                
                changes.append({
                    "symbol": symbol,
                    "old_quantity": old_qty,
                    "new_quantity": new_qty,
                    "diff": diff,
                    "type": change_type
                })
        
        if not changed:
            return False, "no_change", []
        
        # Определить основную причину
        if any(c["type"] == "new_symbol" for c in changes):
            reason = "new_symbol"
        elif any(c["type"] == "symbol_removed" for c in changes):
            reason = "symbol_removed"
        else:
            reason = "quantity_changed"
        
        return True, reason, changes
    
    def track_delta(
        self,
        client_id: str,
        deltas: Dict[str, int],
        prices: Dict[str, float]
    ) -> Tuple[bool, str, List[dict]]:
        """
        Отследить изменение дельты.
        
        Args:
            client_id: ID клиента
            deltas: Текущие дельты {symbol: quantity}
            prices: Текущие цены {symbol: price}
            
        Returns:
            (changed: bool, reason: str, changes: List[dict])
        """
        # Получить предыдущую дельту
        old_deltas = self.get_last_delta(client_id)
        
        # Сравнить
        changed, reason, changes = self.compare_deltas(old_deltas, deltas)
        
        if changed:
            # Рассчитать total estimated
            total_estimated = sum(
                abs(qty) * prices.get(symbol, 0)
                for symbol, qty in deltas.items()
            )
            
            # Создать snapshot
            snapshot = DeltaSnapshot(
                timestamp=datetime.now().isoformat(),
                deltas=deltas,
                prices=prices,
                total_estimated=total_estimated,
                change_reason=reason
            )
            
            # Сохранить в историю
            history = self._load_history(client_id)
            history.append(snapshot.to_dict())
            self._save_history(client_id, history)
            
            # Обновить кэш
            self._last_deltas[client_id] = deltas.copy()
            
            logger.info(f"[MONITOR] Delta changed for {client_id}: {reason}")
            for change in changes:
                logger.info(f"[MONITOR]   {change['symbol']}: {change['old_quantity']} → {change['new_quantity']} "
                            f"({change['diff']:+d})")
        else:
            logger.debug(f"[MONITOR] Delta unchanged for {client_id}")
        
        return changed, reason, changes
    
    def get_current_summary(self, client_id: str) -> Optional[dict]:
        """Получить текущую сводку дельты для клиента"""
        history = self._load_history(client_id)
        if not history:
            return None
        
        return history[-1]
    
    def get_history(self, client_id: str, limit: int = 50) -> List[dict]:
        """Получить историю дельт клиента"""
        history = self._load_history(client_id)
        return history[-limit:] if len(history) > limit else history

    @staticmethod
    def format_delta_message(
        client_name: str,
        deltas: Dict[str, int],
        prices: Dict[str, float],
        changes: List[dict] = None
    ) -> str:
        """
        Форматировать сообщение о дельте для Telegram.
        
        Args:
            client_name: Имя клиента
            deltas: Текущие дельты
            prices: Текущие цены
            changes: Список изменений (если есть)
            
        Returns:
            Отформатированное сообщение
        """
        lines = [f"🔍 <b>Delta Update</b>", f"👤 Client: {client_name}", ""]
        
        # Если есть изменения — показать что изменилось
        if changes:
            lines.append("📊 <b>Changes:</b>")
            for change in changes:
                symbol = change['symbol']
                old_qty = change['old_quantity']
                new_qty = change['new_quantity']
                diff = change['diff']
                change_type = change['type']
                
                if change_type == "new_symbol":
                    lines.append(f"  🆕 {symbol}: +{new_qty}")
                elif change_type == "symbol_removed":
                    lines.append(f"  ❌ {symbol}: removed")
                else:
                    lines.append(f"  {symbol}: {old_qty} → {new_qty} ({diff:+d})")
            lines.append("")
        
        # Группировать по действию
        buys = []
        sells = []
        
        for symbol, qty in deltas.items():
            price = prices.get(symbol, 0)
            cost = abs(qty) * price
            
            if qty > 0:
                buys.append(f"  {symbol}: {qty} shares (~${cost:,.0f})")
            elif qty < 0:
                sells.append(f"  {symbol}: {abs(qty)} shares (~${cost:,.0f})")
        
        if buys:
            lines.append("📈 <b>BUY:</b>")
            lines.extend(buys)
        
        if sells:
            lines.append("📉 <b>SELL:</b>")
            lines.extend(sells)
        
        if not buys and not sells:
            lines.append("✅ No delta (positions in sync)")
        
        # Итого
        total = sum(abs(qty) * prices.get(symbol, 0) for symbol, qty in deltas.items())
        lines.append("")
        lines.append(f"💰 Total: ~${total:,.0f}")
        lines.append(f"🕐 {datetime.now().strftime('%H:%M:%S')}")
        
        # Команды
        lines.append("")
        lines.append("/execute - Live sync")
        lines.append("/simulate - Simulation sync")
        lines.append("/delta - Current delta")
        
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ════════════════════════════════════════════════════════════════

_delta_tracker: Optional[DeltaTracker] = None


def get_delta_tracker() -> DeltaTracker:
    """Получить глобальный экземпляр DeltaTracker"""
    global _delta_tracker
    if _delta_tracker is None:
        _delta_tracker = DeltaTracker()
    return _delta_tracker
