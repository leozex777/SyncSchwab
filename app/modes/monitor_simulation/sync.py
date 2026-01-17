# app/modes/monitor_simulation/sync.py
"""
🔍🔶 MONITOR SIMULATION DELTA - Отслеживание дельты без ордеров (dry cache).

Особенности:
- Использует данные из account_cache_dry.json для клиентов
- Main Account данные берутся из реального API
- НЕ выполняет ордера
- Отслеживает изменения дельты
- Отправляет уведомления при изменении дельты
"""

from typing import Dict, List, Optional
import schwabdev

from app.core.logger import logger
from app.core.sync_common import (
    InvalidAccountHashError,
    get_positions,
    get_equity,
    get_prices
)
from app.core.delta_tracker import get_delta_tracker
from app.models.copier.calculator import PositionCalculator
from app.models.copier.entities import Position, Instrument
from app.modes.base import SyncMode


class MonitorSimulationSync(SyncMode):
    """
    🔍🔶 MONITOR SIMULATION DELTA - Отслеживание дельты без ордеров (dry cache).
    
    Особенности:
    - Main Account: реальные данные из API
    - Slave Account: виртуальные данные из account_cache_dry.json
    - НЕ выполняет ордера
    - Только отслеживает изменения дельты
    """
    
    MODE_ICON = "🔍🔶"
    MODE_NAME = "MONITOR SIMULATION"
    
    def __init__(self, main_client: schwabdev.Client, slave_client: schwabdev.Client, config: Dict):
        super().__init__(main_client, slave_client, config)
        
        self.calculator = PositionCalculator(
            threshold=config.get('threshold', 0.03)
        )
        self.delta_tracker = get_delta_tracker()
    
    def sync(
        self,
        main_account_hash: str,
        slave_account_hash: str,
        skip_history: bool = False
    ) -> Dict:
        """
        Выполнить отслеживание дельты (без ордеров, используя dry cache).
        
        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта (не используется - берём из dry cache)
            skip_history: Не используется в Monitor режиме
            
        Returns:
            Результаты отслеживания
        """
        self.log_start()
        
        try:
            # Рассчитать дельту
            delta_result = self.calculate_delta(main_account_hash)
            
            if delta_result is None:
                return {
                    'status': 'error',
                    'client_id': self.client_id,
                    'error': 'Failed to calculate delta'
                }
            
            deltas = delta_result.get('deltas', {})
            prices = delta_result.get('prices', {})
            
            # Отследить изменения
            changed, reason, changes = self.delta_tracker.track_delta(
                self.client_id, deltas, prices
            )
            
            result = {
                'status': 'tracked',
                'client_id': self.client_id,
                'changed': changed,
                'reason': reason,
                'delta_count': len(deltas),
                'deltas': deltas,
                'prices': prices,
                'total_estimated': delta_result.get('total_estimated', 0)
            }
            
            # Если дельта изменилась — отправить уведомление
            if changed and changes:
                self._send_delta_notification(deltas, prices, changes)
            
            # Логировать завершение
            logger.info(f"{'═' * 50}")
            logger.info(f"{self.MODE_ICON} {self.MODE_NAME} done | Delta: {len(deltas)} symbols | Changed: {changed}")
            
            return result
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            logger.error(f"❌ Monitor Simulation failed: {e}")
            return {
                'status': 'error',
                'client_id': self.client_id,
                'error': str(e)
            }
    
    def calculate_delta(self, main_account_hash: str) -> Optional[Dict]:
        """
        Рассчитать дельту для клиента (используя dry cache для Slave).
        
        Args:
            main_account_hash: Hash главного аккаунта
            
        Returns:
            {
                'deltas': {symbol: quantity},
                'prices': {symbol: price},
                'total_estimated': float
            }
            или None при ошибке
        """
        try:
            # 1. Получить позиции Main из API (реальные данные)
            main_positions = get_positions(self.main_client, main_account_hash, "Main")
            main_equity = get_equity(self.main_client, main_account_hash, "Main")
            
            # 2. Получить позиции Slave из DRY CACHE (виртуальные данные)
            slave_positions = self._get_slave_positions_from_dry_cache()
            slave_equity = self._get_slave_equity_from_dry_cache()
            
            # 3. Рассчитать scale
            scale = self.calculator.calculate_scale(
                main_equity,
                slave_equity,
                method=self.config.get('scale_method', 'DYNAMIC_RATIO'),
                fixed_amount=self.config.get('fixed_amount')
            )
            
            # 4. Рассчитать дельты
            deltas = self.calculator.calculate_all_deltas(
                main_positions,
                slave_positions,
                scale,
                rounding_method=self.config.get('rounding_method', 'ROUND_DOWN')
            )
            
            if not deltas:
                return {
                    'deltas': {},
                    'prices': {},
                    'total_estimated': 0
                }
            
            # 5. Получить цены
            prices = get_prices(main_positions)
            
            # 6. Рассчитать total estimated
            total_estimated = sum(
                abs(qty) * prices.get(symbol, 0)
                for symbol, qty in deltas.items()
            )
            
            logger.debug(f"[MONITOR SIM] Delta calculated: {len(deltas)} symbols, ~${total_estimated:,.0f}")
            
            return {
                'deltas': deltas,
                'prices': prices,
                'total_estimated': total_estimated,
                'scale': scale
            }
            
        except Exception as e:
            logger.error(f"[MONITOR SIM] Error calculating delta: {e}")
            return None
    
    def _get_slave_data_from_dry_cache(self) -> Optional[Dict]:
        """Получить данные клиента из account_cache_dry.json"""
        from app.core.cache_manager import get_simulation_cache
        
        if not self.client_id:
            logger.warning("[MONITOR SIM] No client_id in config")
            return None
        
        dry_cache = get_simulation_cache()
        client_data = dry_cache.get('clients', {}).get(self.client_id)
        
        if not client_data:
            logger.warning(f"[MONITOR SIM] No data for {self.client_id} in dry cache")
            return None
        
        return client_data
    
    def _get_slave_positions_from_dry_cache(self) -> List:
        """Получить виртуальные позиции клиента из dry cache"""
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return []
        
        positions = []
        for p in client_data.get('positions', []):
            # Создать Instrument
            instrument = Instrument(
                symbol=p.get('symbol', ''),
                description='',
                asset_type='EQUITY'
            )
            
            # Создать Position
            pos = Position(
                account_number='',
                instrument=instrument,
                side='LONG',
                quantity=p.get('quantity', 0),
                average_price=p.get('average_price', p.get('price', 0)),
                market_value=p.get('market_value', 0),
                unrealized_pl=p.get('unrealized_pl', 0),
                maintenance_requirement=0
            )
            positions.append(pos)
        
        logger.debug(f"[MONITOR SIM] Slave positions from dry cache: {len(positions)}")
        return positions
    
    def _get_slave_equity_from_dry_cache(self) -> float:
        """Получить виртуальный equity клиента из dry cache"""
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return 0
        
        equity = client_data.get('balances', {}).get('liquidation_value', 0)
        logger.debug(f"[MONITOR SIM] Slave equity from dry cache: ${equity:,.0f}")
        return equity
    
    def _send_delta_notification(
        self,
        deltas: Dict[str, int],
        prices: Dict[str, float],
        changes: List[dict]
    ):
        """
        Отправить уведомление об изменении дельты в Telegram.
        
        Args:
            deltas: Текущие дельты
            prices: Текущие цены
            changes: Список изменений
        """
        try:
            from app.core.telegram_service import get_telegram_service
            from app.core.delta_tracker import DeltaTracker
            
            telegram = get_telegram_service()
            if not telegram.is_enabled():
                return
            
            # Получить имя клиента из config
            client_name = self.config.get('client_name', self.client_id)
            
            # Форматировать сообщение
            message = DeltaTracker.format_delta_message(
                client_name, deltas, prices, changes
            )
            
            # Добавить пометку что это SIMULATION
            message = f"🔶 SIMULATION\n{message}"
            
            # Отправить
            telegram.send_message(message)
            logger.info(f"[MONITOR SIM] Delta notification sent for {client_name}")
            
        except Exception as e:
            logger.error(f"[MONITOR SIM] Failed to send delta notification: {e}")


def track_simulation_delta_for_client(
    main_client: schwabdev.Client,
    slave_client: schwabdev.Client,
    config: Dict,
    main_account_hash: str
) -> Dict:
    """
    Удобная функция для отслеживания дельты одного клиента (simulation).
    
    Args:
        main_client: schwabdev.Client для Main Account
        slave_client: schwabdev.Client для Slave Account (не используется)
        config: Конфигурация клиента
        main_account_hash: Hash главного аккаунта
        
    Returns:
        Результат отслеживания
    """
    monitor = MonitorSimulationSync(main_client, slave_client, config)
    return monitor.sync(main_account_hash, slave_account_hash="")  # slave_hash не нужен
