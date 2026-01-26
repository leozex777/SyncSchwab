
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
            fixed_amount: Optional[float] = None,
            slave_equity_nomin: Optional[float] = None,
            usage_percent: float = 100
    ) -> float:
        """
        Рассчитать коэффициент масштабирования

        Args:
            main_equity: Equity главного аккаунта
            slave_equity: Текущий equity клиентского аккаунта
            method: Метод масштабирования ('DYNAMIC_RATIO' или 'FIXED_AMOUNT')
            fixed_amount: Фиксированная сумма для торговли (если метод FIXED_AMOUNT)
            slave_equity_nomin: Equity клиента на момент настройки FIXED_AMOUNT
            usage_percent: Процент от slave_equity для использования (для DYNAMIC_RATIO)

        Returns:
            Коэффициент масштабирования
        """
        if main_equity <= 0:
            raise ValueError("main_equity must be positive")
        
        if method == 'FIXED_AMOUNT':
            if not fixed_amount or fixed_amount <= 0:
                raise ValueError("fixed_amount must be positive")
            if not slave_equity_nomin or slave_equity_nomin <= 0:
                # Fallback: использовать текущий equity если nomin не задан
                slave_equity_nomin = slave_equity
            
            # Защищённая сумма = equity на момент настройки - выделенная сумма
            protected = slave_equity_nomin - fixed_amount
            # Рабочий equity = текущий equity - защищённая сумма
            working_equity = slave_equity - protected
            
            # Если рабочий equity <= 0, scale = 0 (нет торговли)
            if working_equity <= 0:
                logger.warning(f"[SCALE] Working equity <= 0: slave={slave_equity}, protected={protected}")
                return 0.0
            
            scale = working_equity / main_equity
            logger.debug(f"[SCALE] FIXED_AMOUNT: nomin={slave_equity_nomin}, fixed={fixed_amount}, "
                        f"protected={protected}, working={working_equity}, scale={scale:.4f}")
        else:  # DYNAMIC_RATIO
            # Применить usage_percent
            usage_factor = usage_percent / 100.0
            scale = usage_factor * slave_equity / main_equity
            logger.debug(f"[SCALE] DYNAMIC_RATIO: usage={usage_percent}%, scale={scale:.4f}")

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
                logger.debug(f"{symbol}: Delta {delta} below threshold ({change_pct:.1%})")
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

        # Проверить позиции которые есть у клиента, но нет у main (закрыть)
        main_symbols = {pos.symbol for pos in main_positions}

        for slave_pos in slave_positions:
            if slave_pos.symbol not in main_symbols and slave_pos.quantity > 0:
                # Закрыть позицию
                deltas[slave_pos.symbol] = -int(slave_pos.quantity)

        # DEBUG — детали
        logger.debug(f"Deltas: {deltas}")
        return deltas
