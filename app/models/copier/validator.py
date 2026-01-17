
# validator.py
# app.models.copier.validator

from datetime import datetime, time
from typing import Dict, List, Tuple
import pytz

from app.core.config_cache import ConfigCache


def get_trading_limits() -> dict:
    """Получить лимиты из general_settings.json (через кэш)"""
    settings = ConfigCache.get_general_settings()
    limits = settings.get('trading_limits', {})
    
    return {
        'max_order_size': limits.get('max_order_size', 1000),
        'max_position_value': limits.get('max_position_value', 50000),
        'min_order_value': limits.get('min_order_value', 1),
        'max_orders_per_run': limits.get('max_orders_per_run', 10)
    }


class OrderValidator:
    """Валидация ордеров перед отправкой"""

    def __init__(self):
        """
        Лимиты читаются ТОЛЬКО из general_settings.json.
        Индивидуальные настройки клиентов НЕ переопределяют лимиты.
        """
        # Загрузить глобальные лимиты
        limits = get_trading_limits()
        
        self.MAX_ORDER_SIZE = limits['max_order_size']
        self.MAX_POSITION_VALUE = limits['max_position_value']
        self.MIN_ORDER_VALUE = limits['min_order_value']
        self.MAX_ORDERS_PER_RUN = limits['max_orders_per_run']

    @staticmethod
    def validate_buying_power(
            required_cash: float,
            available_cash: float
    ) -> Tuple[bool, str]:
        """
        Проверить достаточно ли денег

        Returns:
            (is_valid, message)
        """
        if available_cash <= 0:
            return False, f"No available cash for trading (${available_cash:,.2f})"
        
        if required_cash > available_cash:
            return False, f"Insufficient funds: need ${required_cash:,.2f}, have ${available_cash:,.2f}"

        return True, "OK"

    @staticmethod
    def validate_market_hours() -> Tuple[bool, str]:
        """
        Проверить открыт ли рынок (US Eastern Time)

        Returns:
            (is_valid, message)
        """
        # Получить текущее время в US Eastern Time
        eastern = pytz.timezone('US/Eastern')
        now_eastern = datetime.now(eastern)

        # Проверка дня недели (пн-пт)
        if now_eastern.weekday() >= 5:  # Сб-Вс
            return False, "Market closed (weekend)"

        # Проверка времени (9:30 AM - 4:00 PM ET)
        market_open = time(9, 30)
        market_close = time(16, 0)
        current_time = now_eastern.time()

        if not (market_open <= current_time <= market_close):
            return False, f"Market closed (current time ET: {current_time.strftime('%H:%M')})"

        return True, "Market open"

    def validate_order_limits(
            self,
            symbol: str,
            quantity: int,
            price: float
    ) -> Tuple[bool, str, int]:
        """
        Проверить лимиты ордера и обрезать если нужно.

        Args:
            symbol: Тикер символа
            quantity: Количество акций (может быть отрицательным для SELL)
            price: Цена за акцию

        Returns:
            (is_valid, message, adjusted_quantity)
            - is_valid: True если ордер можно выполнить (возможно с обрезкой)
            - message: Сообщение (OK или предупреждение)
            - adjusted_quantity: Скорректированное количество
        """
        abs_quantity = abs(quantity)
        sign = 1 if quantity > 0 else -1
        adjusted_qty = abs_quantity
        warnings = []

        # Максимум акций в ордере — ОБРЕЗАТЬ до лимита
        if abs_quantity > self.MAX_ORDER_SIZE:
            adjusted_qty = self.MAX_ORDER_SIZE
            warnings.append(f"{symbol}: Order size {abs_quantity} → {adjusted_qty} (max limit)")

        # Стоимость позиции
        position_value = adjusted_qty * price

        # Максимальная стоимость — ОБРЕЗАТЬ до лимита
        if position_value > self.MAX_POSITION_VALUE and price > 0:
            max_qty_by_value = int(self.MAX_POSITION_VALUE / price)
            if max_qty_by_value < adjusted_qty:
                adjusted_qty = max_qty_by_value
                warnings.append(f"{symbol}: Position value capped to ${self.MAX_POSITION_VALUE:,.0f}")

        # Минимальная стоимость — ОТКЛОНИТЬ (нельзя обрезать вверх)
        final_value = adjusted_qty * price
        if final_value < self.MIN_ORDER_VALUE:
            return False, f"{symbol}: Value ${final_value:,.2f} below min ${self.MIN_ORDER_VALUE:,.2f}", 0

        # Если количество стало 0 после обрезки
        if adjusted_qty <= 0:
            return False, f"{symbol}: Order reduced to 0", 0

        # Вернуть результат
        if warnings:
            return True, "; ".join(warnings), adjusted_qty * sign
        return True, "OK", quantity

    def validate_all_orders(
            self,
            deltas: Dict[str, int],
            prices: Dict[str, float],
            available_cash: float
    ) -> Tuple[Dict[str, int], List[str]]:
        """
        Валидация всех ордеров с обрезкой до лимитов.

        Returns:
            (valid_deltas, errors_and_warnings)
        """
        buy_orders = {}
        sell_orders = {}
        messages = []  # Ошибки и предупреждения
        total_buy_cost = 0

        # Разделить на покупки и продажи
        for symbol, delta in deltas.items():
            price = prices.get(symbol, 0)

            if price == 0:
                messages.append(f"{symbol}: Price not available")
                continue

            # Проверка лимитов (с обрезкой)
            is_valid, msg, adjusted_qty = self.validate_order_limits(symbol, delta, price)

            if not is_valid:
                messages.append(msg)
                continue
            
            # Добавить предупреждение если было обрезано
            if msg != "OK":
                messages.append(msg)

            if adjusted_qty > 0:  # Покупка
                cost = adjusted_qty * price
                total_buy_cost += cost
                buy_orders[symbol] = adjusted_qty
            elif adjusted_qty < 0:  # Продажа
                sell_orders[symbol] = adjusted_qty

        # Проверка buying power (только для покупок)
        if buy_orders:
            is_valid, msg = self.validate_buying_power(total_buy_cost, available_cash)

            if not is_valid:
                messages.append(msg)
                
                # Уменьшить покупки пропорционально (только если есть деньги)
                if available_cash > 0 and total_buy_cost > 0:
                    ratio = available_cash / total_buy_cost
                    buy_orders = {k: int(v * ratio) for k, v in buy_orders.items()}
                    # Удалить нулевые ордера
                    buy_orders = {k: v for k, v in buy_orders.items() if v > 0}
                else:
                    # Нет денег — отклонить ВСЕ покупки
                    buy_orders = {}

        # Объединить валидные ордера (продажи первыми)
        result_deltas = {**sell_orders, **buy_orders}

        # Проверка количества ордеров
        if len(result_deltas) > self.MAX_ORDERS_PER_RUN:
            messages.append(f"Too many orders: {len(result_deltas)} → {self.MAX_ORDERS_PER_RUN} (max limit)")
            # Взять первые MAX_ORDERS_PER_RUN (продажи уже первыми)
            result_deltas = dict(list(result_deltas.items())[:self.MAX_ORDERS_PER_RUN])

        return result_deltas, messages
