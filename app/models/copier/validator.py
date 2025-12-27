
# validator.py
# app.models.copier.validator

from datetime import datetime, time
from typing import Dict, List, Tuple
import pytz

from app.core.json_utils import load_json


def get_trading_limits() -> dict:
    """Получить лимиты из general_settings.json"""
    settings = load_json("config/general_settings.json", default={})
    limits = settings.get('trading_limits', {})
    
    return {
        'max_order_size': limits.get('max_order_size', 1000),
        'max_position_value': limits.get('max_position_value', 50000),
        'min_order_value': limits.get('min_order_value', 1),
        'max_orders_per_run': limits.get('max_orders_per_run', 10)
    }


class OrderValidator:
    """Валидация ордеров перед отправкой"""

    def __init__(self, config: dict = None):
        """
        Args:
            config: Опциональный конфиг клиента (для переопределения)
        """
        # Загрузить глобальные лимиты
        limits = get_trading_limits()
        
        # Использовать глобальные лимиты, но позволить переопределить из config клиента
        self.MAX_ORDER_SIZE = config.get('max_order_size', limits['max_order_size']) if config else limits['max_order_size']
        self.MAX_POSITION_VALUE = config.get('max_position_value', limits['max_position_value']) if config else limits['max_position_value']
        self.MIN_ORDER_VALUE = config.get('min_order_value', limits['min_order_value']) if config else limits['min_order_value']
        self.MAX_ORDERS_PER_RUN = config.get('max_orders_per_run', limits['max_orders_per_run']) if config else limits['max_orders_per_run']

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
    ) -> Tuple[bool, str]:
        """
        Проверить лимиты ордера

        Args:
            symbol: Тикер символа
            quantity: Количество акций (может быть отрицательным для SELL)
            price: Цена за акцию

        Returns:
            (is_valid, message)
        """
        abs_quantity = abs(quantity)

        # Максимум акций в ордере
        if abs_quantity > self.MAX_ORDER_SIZE:
            return False, f"{symbol}: Order size {abs_quantity} exceeds max {self.MAX_ORDER_SIZE}"

        # Стоимость позиции
        position_value = abs_quantity * price

        if position_value > self.MAX_POSITION_VALUE:
            return False, f"{symbol}: Position value ${position_value:,.2f} exceeds max ${self.MAX_POSITION_VALUE:,.2f}"

        if position_value < self.MIN_ORDER_VALUE:
            return False, f"{symbol}: Position value ${position_value:,.2f} below min ${self.MIN_ORDER_VALUE:,.2f}"

        return True, "OK"

    def validate_all_orders(
            self,
            deltas: Dict[str, int],
            prices: Dict[str, float],
            available_cash: float
    ) -> Tuple[Dict[str, int], List[str]]:
        """
        Валидация всех ордеров

        Returns:
            (valid_deltas, errors)
        """
        buy_orders = {}
        sell_orders = {}
        errors = []
        total_buy_cost = 0

        # Разделить на покупки и продажи
        for symbol, delta in deltas.items():
            price = prices.get(symbol, 0)

            if price == 0:
                errors.append(f"{symbol}: Price not available")
                continue

            # Проверка лимитов
            is_valid, msg = self.validate_order_limits(symbol, delta, price)

            if not is_valid:
                errors.append(msg)
                continue

            if delta > 0:  # Покупка
                cost = delta * price
                total_buy_cost += cost
                buy_orders[symbol] = delta
            else:  # Продажа
                sell_orders[symbol] = delta

        # Проверка buying power (только для покупок)
        if buy_orders:
            is_valid, msg = self.validate_buying_power(total_buy_cost, available_cash)

            if not is_valid:
                errors.append(msg)
                
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
            errors.append(f"Too many orders: {len(result_deltas)} > {self.MAX_ORDERS_PER_RUN}")
            # Взять первые MAX_ORDERS_PER_RUN (продажи уже первыми)
            result_deltas = dict(list(result_deltas.items())[:self.MAX_ORDERS_PER_RUN])

        return result_deltas, errors
