# app/modes/simulation/sync.py
"""
🔶 SIMULATION MODE - Виртуальные ордера с dry cache.

Особенности:
- Main Account данные берутся из реального API
- Slave Account данные берутся из account_cache_dry.json
- НЕ отправляет реальные ордера
- Обновляет dry cache после каждой синхронизации
- История сохраняется в {client_id}_history_dry.json
"""

from typing import Dict, List, Optional
import schwabdev

from app.core.logger import logger
from app.core.sync_common import (
    InvalidAccountHashError,
    get_notification_settings,
    get_positions,
    get_equity,
    get_prices,
    build_sync_result,
    save_sync_result
)
from app.core.notification_service import get_notification_service
from app.models.copier.calculator import PositionCalculator
from app.models.copier.validator import OrderValidator
from app.models.copier.entities import Position, Instrument
from app.modes.base import SyncMode


class SimulationSync(SyncMode):
    """
    🔶 SIMULATION MODE - Виртуальные ордера с dry cache.
    
    Особенности:
    - Main Account: реальные данные из API
    - Slave Account: виртуальные данные из account_cache_dry.json
    - НЕ отправляет реальные ордера
    - Обновляет dry cache после каждой синхронизации
    - История сохраняется в {client_id}_history_dry.json
    """
    
    MODE_ICON = "🔶"
    MODE_NAME = "SIMULATION"
    
    def __init__(self, main_client: schwabdev.Client, slave_client: schwabdev.Client, config: Dict):
        super().__init__(main_client, slave_client, config)
        
        self.calculator = PositionCalculator(
            threshold=config.get('threshold', 0.03)
        )
        self.validator = OrderValidator()
    
    def sync(
        self,
        main_account_hash: str,
        slave_account_hash: str,
        skip_history: bool = False
    ) -> Dict:
        """
        Выполнить SIMULATION синхронизацию.
        
        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта (не используется - берём из dry cache)
            skip_history: Пропустить запись в историю
            
        Returns:
            Результаты синхронизации
        """
        self.log_start()
        
        # Получить настройки уведомлений
        notif_settings = get_notification_settings()
        notif = get_notification_service()
        
        # Уведомление о начале (только если toast_on_success включен)
        if notif_settings['toast_on_success']:
            notif.info(f"{self.MODE_ICON} Sync started ({self.MODE_NAME})")
        
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
                fixed_amount=self.config.get('fixed_amount'),
                slave_equity_nomin=self.config.get('slave_equity_nomin'),
                usage_percent=self.config.get('usage_percent', 100)
            )
            
            # 4. Рассчитать дельты
            deltas = self.calculator.calculate_all_deltas(
                main_positions,
                slave_positions,
                scale,
                rounding_method=self.config.get('rounding_method', 'ROUND_DOWN')
            )
            
            if not deltas:
                logger.info("[SIMULATION] ✅ All positions are in sync, no orders needed")
                return build_sync_result(
                    operating_mode='simulation',
                    scale=scale,
                    main_equity=main_equity,
                    slave_equity=slave_equity,
                    deltas=deltas,
                    valid_deltas={},
                    results=[],
                    status="SUCCESS"
                )
            
            # 5. Получить цены
            prices = get_prices(main_positions)
            
            # 6. Получить доступные средства из dry cache
            available_cash = self._get_slave_available_cash_from_dry_cache()
            
            # 7. Валидировать ордера
            valid_deltas, errors = self.validator.validate_all_orders(
                deltas,
                prices,
                available_cash
            )
            
            # 8. Выполнить ВИРТУАЛЬНЫЕ ордера (обновить dry cache)
            results = []
            if valid_deltas:
                logger.info("🔶 SIMULATION MODE: Executing virtual orders!")
                results = self._execute_virtual_orders(valid_deltas, prices)
                
                # Обновить dry cache
                self._update_dry_cache_after_simulation(valid_deltas, prices)
            
            # 9. Сформировать результат
            sync_result = build_sync_result(
                operating_mode='simulation',
                scale=scale,
                main_equity=main_equity,
                slave_equity=slave_equity,
                deltas=deltas,
                valid_deltas=valid_deltas,
                results=results,
                status='SUCCESS',
                errors=errors
            )
            
            # 10. Сохранить в историю (если не пропускаем)
            if not skip_history:
                save_sync_result(sync_result, self.client_id, 'simulation')
            else:
                logger.debug("History write skipped")
            
            # Логировать завершение
            self.log_complete(len(results), scale)
            
            return sync_result
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            logger.error(f"❌ SIMULATION Sync failed: {e}")
            raise
    
    # ═══════════════════════════════════════════════════════════════
    # МЕТОДЫ ДЛЯ РАБОТЫ С DRY CACHE
    # ═══════════════════════════════════════════════════════════════
    
    def _get_slave_data_from_dry_cache(self) -> Optional[Dict]:
        """Получить данные клиента из account_cache_dry.json"""
        from app.core.cache_manager import get_simulation_cache
        
        if not self.client_id:
            logger.warning("[SIMULATION] No client_id in config")
            return None
        
        dry_cache = get_simulation_cache()
        client_data = dry_cache.get('clients', {}).get(self.client_id)
        
        if not client_data:
            logger.warning(f"[SIMULATION] No data for {self.client_id} in dry cache")
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
        
        logger.debug(f"[SIMULATION] Slave positions from dry cache: {len(positions)}")
        return positions
    
    def _get_slave_equity_from_dry_cache(self) -> float:
        """Получить виртуальный equity клиента из dry cache"""
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return 0
        
        equity = client_data.get('balances', {}).get('liquidation_value', 0)
        logger.debug(f"[SIMULATION] Slave equity from dry cache: ${equity:,.0f}")
        return equity
    
    def _get_slave_available_cash_from_dry_cache(self) -> float:
        """Получить доступные средства из dry cache"""
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return 0
        
        balances = client_data.get('balances', {})
        
        # Использовать available_funds или cash_balance
        available = balances.get('available_funds', balances.get('cash_balance', 0))
        
        # Учесть маржу если включена
        if self.config.get('use_margin', False):
            margin_percent = self.config.get('margin_percent', 0)
            if margin_percent > 0:
                available = available * (1 + margin_percent / 100)
        
        logger.debug(f"[SIMULATION] Available cash from dry cache: ${available:,.0f}")
        return available
    
    def _execute_virtual_orders(
        self,
        deltas: Dict[str, int],
        prices: Dict[str, float]
    ) -> List[Dict]:
        """
        Выполнить виртуальные ордера (только логирование).
        
        Returns:
            Список результатов ордеров
        """
        results = []
        
        for symbol, delta in deltas.items():
            price = prices.get(symbol, 0)
            action = "BUY" if delta > 0 else "SELL"
            qty = abs(delta)
            value = qty * price
            
            logger.info(f"[SIMULATION] 🔶 {action} {qty} {symbol} @ ${price:.2f} = ${value:,.2f}")
            
            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': qty,
                'price': price,
                'value': value,
                'status': 'VIRTUAL',
                'order_id': f'SIM_{symbol}_{qty}'
            })
        
        return results
    
    def _update_dry_cache_after_simulation(
        self,
        deltas: Dict[str, int],
        prices: Dict[str, float]
    ):
        """Обновить account_cache_dry.json после виртуальных ордеров"""
        from app.core.cache_manager import get_simulation_cache, update_simulation_cache
        
        if not self.client_id:
            logger.warning("[SIMULATION] Cannot update dry cache: no client_id")
            return
        
        try:
            dry_cache = get_simulation_cache()
            client_data = dry_cache.get('clients', {}).get(self.client_id)
            
            if not client_data:
                logger.warning(f"[SIMULATION] No client data in dry cache for {self.client_id}")
                return
            
            positions = client_data.get('positions', [])
            balances = client_data.get('balances', {})
            cash_balance = float(balances.get('cash_balance', 0))
            
            # Создать словарь позиций для быстрого доступа
            positions_dict = {p['symbol']: p for p in positions}
            
            total_buy_value = 0
            total_sell_value = 0
            
            for symbol, delta in deltas.items():
                price = prices.get(symbol, 0)
                order_value = abs(delta) * price
                
                if delta > 0:  # BUY
                    total_buy_value += order_value
                    
                    if symbol in positions_dict:
                        # Увеличить существующую позицию
                        old_qty = positions_dict[symbol]['quantity']
                        old_avg_price = positions_dict[symbol].get('average_price', price)
                        new_qty = old_qty + delta
                        new_avg_price = ((old_qty * old_avg_price) + (delta * price)) / new_qty
                        
                        positions_dict[symbol]['quantity'] = new_qty
                        positions_dict[symbol]['average_price'] = round(new_avg_price, 4)
                        positions_dict[symbol]['price'] = price
                        positions_dict[symbol]['market_value'] = new_qty * price
                    else:
                        # Создать новую позицию
                        positions_dict[symbol] = {
                            'symbol': symbol,
                            'quantity': delta,
                            'price': price,
                            'average_price': price,
                            'market_value': delta * price,
                            'unrealized_pl': 0
                        }
                        
                elif delta < 0:  # SELL
                    total_sell_value += order_value
                    
                    if symbol in positions_dict:
                        old_qty = positions_dict[symbol]['quantity']
                        new_qty = old_qty + delta  # delta отрицательный
                        
                        if new_qty <= 0:
                            # Позиция закрыта
                            del positions_dict[symbol]
                        else:
                            positions_dict[symbol]['quantity'] = new_qty
                            positions_dict[symbol]['market_value'] = new_qty * price
                            positions_dict[symbol]['price'] = price
            
            # Обновить баланс
            new_cash_balance = cash_balance - total_buy_value + total_sell_value
            new_positions = list(positions_dict.values())
            total_market_value = sum(p.get('market_value', 0) for p in new_positions)
            new_liquidation_value = new_cash_balance + total_market_value
            
            # Обновить данные клиента
            client_data['positions'] = new_positions
            client_data['positions_count'] = len(new_positions)
            client_data['balances']['cash_balance'] = round(new_cash_balance, 2)
            client_data['balances']['liquidation_value'] = round(new_liquidation_value, 2)
            client_data['balances']['available_funds'] = round(new_cash_balance, 2)
            client_data['total_pl'] = 0
            
            # Сохранить
            dry_cache['clients'][self.client_id] = client_data
            update_simulation_cache(dry_cache)
            
            logger.info(f"[SIMULATION] Dry cache updated: {len(new_positions)} positions, "
                        f"cash=${new_cash_balance:,.0f}")
            
        except Exception as e:
            logger.error(f"[SIMULATION] Failed to update dry cache: {e}")
