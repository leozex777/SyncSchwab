
# calculator.py
# app.models.copier.calculator

from typing import Dict, Optional
from app.models.copier.entities import Position
from app.core.logger import logger


class PositionCalculator:
    """Калькулятор для расчета целевых позиций и дельт"""

    def __init__(self, threshold: float = 0.03):
        """
        Args:
            threshold: Порог синхронизации (по умолчанию 3%)
        """
        self.threshold = threshold

    @staticmethod
    def calculate_scale(
            main_equity: float,
            slave_equity: float,
            method: str = 'DYNAMIC_RATIO',
            fixed_amount: Optional[float] = None
    ) -> float:
        """
        Рассчитать коэффициент масштабирования

        Args:
            main_equity: Equity главного аккаунта
            slave_equity: Equity клиентского аккаунта
            method: Метод масштабирования ('DYNAMIC_RATIO' или 'FIXED_AMOUNT')
            fixed_amount: Фиксированная сумма (если метод FIXED_AMOUNT)

        Returns:
            Коэффициент масштабирования
        """
        if method == 'FIXED_AMOUNT':
            if not fixed_amount or fixed_amount <= 0:
                raise ValueError("fixed_amount must be positive")
            if main_equity <= 0:
                raise ValueError("main_equity must be positive")
            scale = fixed_amount / main_equity
        else:  # DYNAMIC_RATIO
            if main_equity <= 0:
                raise ValueError("main_equity must be positive")
            scale = slave_equity / main_equity

        logger.info(f"📊 Scale calculated: {scale:.4f} ({scale * 100:.2f}%)")
        return scale

    @staticmethod
    def calculate_target_quantity(
            main_quantity: float,
            scale: float,
            rounding_method: str = 'ROUND_DOWN'
    ) -> int:
        """
        Рассчитать целевое количество акций

        Args:
            main_quantity: Количество на главном аккаунте
            scale: Коэффициент масштабирования
            rounding_method: Метод округления ('ROUND_DOWN', 'ROUND_NEAREST', 'ROUND_UP')

        Returns:
            Целевое количество (int)
        """
        target = main_quantity * scale

        if rounding_method == 'ROUND_UP':
            return int(target) + (1 if target % 1 > 0 else 0)
        elif rounding_method == 'ROUND_NEAREST':
            return round(target)
        else:  # ROUND_DOWN (default)
            return int(target)

    def calculate_delta(
            self,
            target_quantity: int,
            current_quantity: float,
            symbol: str
    ) -> int:
        """
        Рассчитать разницу между целевым и текущим количеством

        Args:
            target_quantity: Целевое количество
            current_quantity: Текущее количество
            symbol: Символ акции

        Returns:
            Дельта (положительная = покупка, отрицательная = продажа)
        """
        delta = target_quantity - int(current_quantity)

        # Проверка порога
        if current_quantity > 0:
            change_pct = abs(delta) / current_quantity
            if change_pct < self.threshold:
                logger.debug(f"  {symbol}: Delta {delta} below threshold ({change_pct:.1%} < {self.threshold:.1%})")
                return 0

        return delta

    def calculate_all_deltas(
            self,
            main_positions: list[Position],
            slave_positions: list[Position],
            scale: float,
            rounding_method: str = 'ROUND_DOWN'
    ) -> Dict[str, int]:
        """
        Рассчитать дельты для всех позиций

        Args:
            main_positions: Позиции главного аккаунта
            slave_positions: Позиции клиентского аккаунта
            scale: Коэффициент масштабирования
            rounding_method: Метод округления

        Returns:
            Словарь {symbol: delta}
        """
        deltas = {}

        # Создать словарь текущих позиций клиента
        slave_dict = {pos.symbol: pos.quantity for pos in slave_positions}

        # Рассчитать дельты для всех позиций main
        for main_pos in main_positions:
            symbol = main_pos.symbol

            # Целевое количество
            target_qty = self.calculate_target_quantity(
                main_pos.quantity,
                scale,
                rounding_method
            )

            # Текущее количество у клиента
            current_qty = slave_dict.get(symbol, 0)

            # Дельта
            delta = self.calculate_delta(target_qty, current_qty, symbol)

            if delta != 0:
                deltas[symbol] = delta
                # ИСПРАВЛЕНО: определяем action перед использованием
                action = "BUY" if delta > 0 else "SELL"
                logger.info(f"  {symbol}: {action} {abs(delta)} (target: {target_qty}, current: {int(current_qty)})")

        # Проверить позиции которые есть у клиента, но нет у main (закрыть)
        main_symbols = {pos.symbol for pos in main_positions}

        for slave_pos in slave_positions:
            if slave_pos.symbol not in main_symbols and slave_pos.quantity > 0:
                # Закрыть позицию
                deltas[slave_pos.symbol] = -int(slave_pos.quantity)
                logger.info(f"  {slave_pos.symbol}: CLOSE position (SELL {int(slave_pos.quantity)})")

        logger.info(f"📊 Total deltas: {len(deltas)}")
        return deltas