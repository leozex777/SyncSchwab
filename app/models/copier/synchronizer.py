# synchronizer.py
# app.models.copier.synchronizer
#
# РЕФАКТОРИНГ v2.0: Диспетчер режимов синхронизации
#
# Этот файл теперь является диспетчером, который вызывает соответствующий
# класс из app/modes/ в зависимости от operating_mode.
#
# Режимы:
# - live → modes/live/LiveSync
# - simulation → LEGACY код (пока не реализован в modes/)
# - monitor → modes/monitor_live/ или modes/monitor_simulation/

from typing import Dict, List, Optional
import schwabdev
from datetime import datetime

from app.core.logger import logger
from app.core.config_cache import ConfigCache
from app.core.notification_service import get_notification_service

# Импорт из sync_common
from app.core.sync_common import (
    InvalidAccountHashError,
    get_notification_settings,
    get_prices
)

# Импорт классов режимов
from app.modes.live import LiveSync


class PositionSynchronizer:
    """
    Диспетчер синхронизации позиций.
    
    Определяет режим работы и делегирует выполнение соответствующему
    классу из app/modes/.
    
    Поддерживаемые режимы:
    - 'live': Реальные ордера через LiveSync
    - 'simulation': LEGACY код (будет мигрирован позже)
    - 'dry_run': LEGACY код
    """

    def __init__(
            self,
            main_client: schwabdev.Client,
            slave_client: schwabdev.Client,
            config: Dict,
            operating_mode: str = 'dry_run'
    ):
        """
        Args:
            main_client: Client для главного аккаунта
            slave_client: Client для клиентского аккаунта
            config: Конфигурация синхронизации
            operating_mode: Режим работы ('dry_run', 'simulation', 'live')
        """
        self.main_client = main_client
        self.slave_client = slave_client
        self.config = config
        self.operating_mode = operating_mode
        
        # Для LEGACY режимов (simulation, dry_run)
        from app.models.copier.calculator import PositionCalculator
        from app.models.copier.validator import OrderValidator
        
        self.calculator = PositionCalculator(
            threshold=config.get('threshold', 0.03)
        )
        self.validator = OrderValidator()

    def sync(
            self,
            main_account_hash: str,
            slave_account_hash: str,
            skip_history: bool = False,
            skip_execution: bool = False
    ) -> Dict:
        """
        Выполнить синхронизацию.
        
        Диспетчер определяет режим и вызывает соответствующий класс.

        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта
            skip_history: Пропустить запись в историю
            skip_execution: Пропустить выполнение ордеров (для Monitor режима)

        Returns:
            Результаты синхронизации
        """
        # ═══════════════════════════════════════════════════════════════
        # LIVE MODE → Делегировать в modes/live/LiveSync
        # ═══════════════════════════════════════════════════════════════
        if self.operating_mode == 'live':
            logger.debug("[DISPATCHER] Routing to LiveSync")
            
            live_sync = LiveSync(
                main_client=self.main_client,
                slave_client=self.slave_client,
                config=self.config
            )
            
            return live_sync.sync(
                main_account_hash=main_account_hash,
                slave_account_hash=slave_account_hash,
                skip_history=skip_history
            )
        
        # ═══════════════════════════════════════════════════════════════
        # SIMULATION MODE → LEGACY код (пока не мигрирован)
        # ═══════════════════════════════════════════════════════════════
        elif self.operating_mode == 'simulation':
            logger.debug("[DISPATCHER] Using LEGACY simulation code")
            return self._legacy_sync(main_account_hash, slave_account_hash, skip_history, skip_execution)
        
        # ═══════════════════════════════════════════════════════════════
        # DRY RUN MODE → LEGACY код
        # ═══════════════════════════════════════════════════════════════
        else:
            logger.debug("[DISPATCHER] Using LEGACY dry_run code")
            return self._legacy_sync(main_account_hash, slave_account_hash, skip_history, skip_execution)

    # ═══════════════════════════════════════════════════════════════════════
    # LEGACY КОД: Будет удалён после миграции simulation
    # ═══════════════════════════════════════════════════════════════════════
    
    def _legacy_sync(
            self,
            main_account_hash: str,
            slave_account_hash: str,
            skip_history: bool = False,
            skip_execution: bool = False
    ) -> Dict:
        """
        LEGACY: Старая логика синхронизации для simulation и dry_run.
        
        Будет удалена после миграции simulation в modes/simulation/.
        
        Args:
            skip_execution: Если True, не выполнять ордера и не обновлять dry_cache
                           (используется для Monitor режима)
        """
        
        # Проверить является ли это Monitor режимом
        is_monitor = self.config.get('is_monitor', False)
        monitor_sync_mode = self.config.get('monitor_sync_mode', 'live')
        
        if is_monitor:
            if monitor_sync_mode == 'simulation':
                mode_icon, mode_str = ('🔍 🔶', 'Monitor Simulation Delta')
            else:
                mode_icon, mode_str = ('🔍 🔴', 'Monitor Live Delta')
        else:
            mode_icons = {
                'dry_run': ('🧪', 'DRY RUN'),
                'simulation': ('🔶', 'SIMULATION'),
                'live': ('🔴', 'LIVE')
            }
            mode_icon, mode_str = mode_icons.get(self.operating_mode, ('❓', 'UNKNOWN'))
        
        # Получить настройки уведомлений
        notif_settings = get_notification_settings()
        notif = get_notification_service()
        
        if notif_settings['toast_on_success'] and not is_monitor:
            notif.info(f"{mode_icon} Sync started ({mode_str})")
        
        logger.debug(f"{mode_icon} {mode_str} sync started (LEGACY)")

        try:
            # 1. Получить позиции
            main_positions = self._get_positions(self.main_client, main_account_hash, "Main")
            
            if self.operating_mode == 'simulation':
                slave_positions = self._get_slave_positions_from_dry_cache()
                logger.debug(f"[SIMULATION] Using dry cache for Slave positions")
            else:
                slave_positions = self._get_positions(self.slave_client, slave_account_hash, "Slave")

            # 2. Получить equity
            main_equity = self._get_equity(self.main_client, main_account_hash, "Main")
            
            if self.operating_mode == 'simulation':
                slave_equity = self._get_slave_equity_from_dry_cache()
            else:
                slave_equity = self._get_equity(self.slave_client, slave_account_hash, "Slave")

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
                logger.info("[SYNC] ✅ All positions are in sync, no orders needed")
                return self._build_result(
                    scale, main_equity, slave_equity,
                    deltas, {}, [], "SUCCESS"
                )

            # 5. Получить цены
            prices = get_prices(main_positions)

            # 6. Получить доступные средства
            if self.operating_mode == 'simulation':
                available_cash = self._get_slave_available_cash_from_dry_cache()
            else:
                available_cash = self._get_available_cash(self.slave_client, slave_account_hash)

            # 7. Валидировать ордера
            valid_deltas, errors = self.validator.validate_all_orders(
                deltas,
                prices,
                available_cash
            )

            # 8. Выполнить ордера (если не skip_execution)
            if skip_execution:
                # Monitor режим: только рассчитать дельту, не выполнять
                results = []
                logger.debug(f"[MONITOR] Execution skipped (skip_execution=True)")
            elif self.operating_mode == 'simulation' and valid_deltas:
                logger.info("🔶 SIMULATION: Showing what would be executed...")
                results = self._simulate_live_orders(valid_deltas, prices)
                self._update_dry_cache_after_simulation(valid_deltas, prices)
            else:
                # DRY RUN
                results = self._dry_run_orders(valid_deltas, prices)

            # 9. Сохранить результат
            status_map = {
                'dry_run': 'DRY_RUN',
                'simulation': 'SIMULATED',
                'live': 'SUCCESS'
            }
            sync_result = self._build_result(
                scale, main_equity, slave_equity,
                deltas, valid_deltas, results,
                status_map.get(self.operating_mode, 'UNKNOWN'),
                errors
            )
            
            # Добавить prices в результат (для Monitor режима)
            sync_result['prices'] = prices

            if not skip_history:
                self._save_sync_result(sync_result)
            else:
                logger.debug("History write skipped")

            logger.info(f"{'═' * 50}")
            logger.info(f"{mode_icon} {mode_str} done | {len(results)} orders | Scale {scale*100:.1f}%")
            
            if self.operating_mode != 'simulation':
                self._update_cache_after_sync(main_positions, slave_positions, main_equity, slave_equity)

            return sync_result

        except InvalidAccountHashError:
            raise
        except Exception as e:
            logger.error(f"❌ Synchronization failed: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════
    # LEGACY HELPER METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_positions(
            self,
            client: schwabdev.Client,
            account_hash: str,
            label: str
    ) -> List:
        """Получить позиции аккаунта"""
        from app.models.copier.entities import parse_positions_from_account_details
        
        logger.debug(f"Getting {label} positions...")

        try:
            response = client.account_details(account_hash, fields='positions')
            
            if self._is_invalid_hash_error(response):
                logger.error(f"❌ Invalid account hash for {label}")
                raise InvalidAccountHashError(f"Invalid account hash for {label}")
            
            details = response.json()
            positions = parse_positions_from_account_details(details)

            logger.debug(f"{label}: {len(positions)} positions")
            return positions
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            if self._is_hash_error_message(str(e)):
                raise InvalidAccountHashError(f"Invalid account hash for {label}: {e}")
            raise

    def _get_equity(
            self,
            client: schwabdev.Client,
            account_hash: str,
            label: str
    ) -> float:
        """Получить equity аккаунта"""
        try:
            response = client.account_details(account_hash)
            
            if self._is_invalid_hash_error(response):
                raise InvalidAccountHashError(f"Invalid account hash for {label}")
            
            details = response.json()
            sa = details.get('securitiesAccount', {})
            equity = sa.get('currentBalances', {}).get('liquidationValue', 0)

            logger.debug(f"{label} Equity: ${equity:,.2f}")
            return equity
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            if self._is_hash_error_message(str(e)):
                raise InvalidAccountHashError(f"Invalid account hash for {label}: {e}")
            raise

    def _get_available_cash(
            self,
            client: schwabdev.Client,
            account_hash: str
    ) -> float:
        """Получить доступные средства с учетом настроек маржи"""
        try:
            response = client.account_details(account_hash, fields='positions')
            
            if self._is_invalid_hash_error(response):
                raise InvalidAccountHashError("Invalid account hash for slave")
            
            details = response.json()
            sa = details.get('securitiesAccount', {})
            balances = sa.get('currentBalances', {})
            
            buying_power = balances.get('buyingPower', 0)
            cash_balance = balances.get('cashBalance', 0)
            total_value = balances.get('liquidationValue', 0)
            
            positions = sa.get('positions', [])
            positions_value = sum(p.get('marketValue', 0) for p in positions)
            
            logger.debug(f"Balances: Total=${total_value:,.0f}, Cash=${cash_balance:,.0f}, BP=${buying_power:,.0f}")
            
            if buying_power == 0:
                available = cash_balance
                logger.debug(f"Using cashBalance: ${available:,.0f}")
                return available
            
            use_margin = self.config.get('use_margin', False)
            margin_percent = self.config.get('margin_percent', 0)
            schwab_allows_margin = buying_power > cash_balance * 1.1
            
            if not use_margin:
                available = cash_balance
                logger.debug(f"Margin disabled, using cashBalance: ${available:,.0f}")
            elif use_margin and not schwab_allows_margin:
                available = cash_balance
                logger.warning(f"⚠️ Margin requested but NOT available from Schwab")
            elif use_margin and schwab_allows_margin and margin_percent > 0:
                user_limit = total_value * (1 + margin_percent / 100)
                max_allowed = min(buying_power, user_limit)
                available = max(0.0, max_allowed - positions_value)
                logger.debug(f"Margin {margin_percent}%: Available ${available:,.0f}")
            else:
                available = cash_balance
            
            return available
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            if self._is_hash_error_message(str(e)):
                raise InvalidAccountHashError(f"Invalid account hash: {e}")
            raise

    @staticmethod
    def _is_invalid_hash_error(response) -> bool:
        """Проверить является ли ответ ошибкой invalid hash"""
        try:
            if hasattr(response, 'status_code'):
                if response.status_code in [400, 401, 403, 404]:
                    text = response.text.lower() if hasattr(response, 'text') else ''
                    if any(word in text for word in ['invalid', 'hash', 'account', 'not found']):
                        return True
            return False
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _is_hash_error_message(error_msg: str) -> bool:
        """Проверить содержит ли сообщение об ошибке указание на invalid hash"""
        error_lower = error_msg.lower()
        keywords = ['invalid account', 'account not found', 'invalid hash', 'bad request', 'unauthorized']
        return any(keyword in error_lower for keyword in keywords)

    # ═══════════════════════════════════════════════════════════════════════
    # SIMULATION: Методы для чтения из account_cache_dry.json
    # ═══════════════════════════════════════════════════════════════════════

    def _get_slave_data_from_dry_cache(self) -> Optional[Dict]:
        """Получить данные клиента из account_cache_dry.json"""
        from app.core.cache_manager import get_simulation_cache
        
        client_id = self.config.get('client_id')
        if not client_id:
            logger.warning("[SIMULATION] No client_id in config")
            return None
        
        dry_cache = get_simulation_cache()
        client_data = dry_cache.get('clients', {}).get(client_id)
        
        if not client_data:
            logger.warning(f"[SIMULATION] No data for {client_id} in dry cache")
            return None
        
        return client_data

    def _get_slave_positions_from_dry_cache(self) -> List:
        """Получить виртуальные позиции клиента из dry cache"""
        from app.models.copier.entities import Position, Instrument
        
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return []
        
        positions = []
        for p in client_data.get('positions', []):
            instrument = Instrument(
                symbol=p.get('symbol', ''),
                description='',
                asset_type='EQUITY'
            )
            
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
        """Получить виртуальные доступные средства клиента из dry cache"""
        client_data = self._get_slave_data_from_dry_cache()
        if not client_data:
            return 0
        
        balances = client_data.get('balances', {})
        cash_balance = balances.get('cash_balance', 0)
        buying_power = balances.get('buying_power', 0)
        
        if buying_power == 0:
            available = cash_balance
        else:
            use_margin = self.config.get('use_margin', False)
            margin_percent = self.config.get('margin_percent', 0)
            
            if use_margin and margin_percent > 0:
                total_value = float(balances.get('liquidation_value', 0))
                positions_value = sum(
                    float(p.get('market_value', 0))
                    for p in client_data.get('positions', [])
                )
                user_limit = total_value * (1 + margin_percent / 100)
                max_allowed = min(float(buying_power), user_limit)
                available = max(0.0, max_allowed - positions_value)
            else:
                available = cash_balance
        
        logger.debug(f"[SIMULATION] Slave available cash from dry cache: ${available:,.0f}")
        return available

    def _update_dry_cache_after_simulation(self, deltas: Dict[str, int], prices: Dict[str, float]):
        """Обновить account_cache_dry.json после виртуальных ордеров"""
        from app.core.cache_manager import get_simulation_cache, update_simulation_cache
        
        client_id = self.config.get('client_id')
        if not client_id:
            logger.warning("[SIMULATION] Cannot update dry cache: no client_id")
            return
        
        try:
            dry_cache = get_simulation_cache()
            client_data = dry_cache.get('clients', {}).get(client_id)
            
            if not client_data:
                logger.warning(f"[SIMULATION] No client data in dry cache for {client_id}")
                return
            
            positions = client_data.get('positions', [])
            balances = client_data.get('balances', {})
            cash_balance = float(balances.get('cash_balance', 0))
            
            positions_dict = {p['symbol']: p for p in positions}
            
            total_buy_value = 0
            total_sell_value = 0
            
            for symbol, delta in deltas.items():
                price = prices.get(symbol, 0)
                order_value = abs(delta) * price
                
                if delta > 0:
                    total_buy_value += order_value
                    
                    if symbol in positions_dict:
                        old_qty = positions_dict[symbol]['quantity']
                        old_avg_price = positions_dict[symbol].get('average_price', price)
                        new_qty = old_qty + delta
                        new_avg_price = ((old_qty * old_avg_price) + (delta * price)) / new_qty
                        
                        positions_dict[symbol]['quantity'] = new_qty
                        positions_dict[symbol]['average_price'] = round(new_avg_price, 4)
                        positions_dict[symbol]['price'] = price
                        positions_dict[symbol]['market_value'] = new_qty * price
                    else:
                        positions_dict[symbol] = {
                            'symbol': symbol,
                            'quantity': delta,
                            'price': price,
                            'average_price': price,
                            'market_value': delta * price,
                            'unrealized_pl': 0
                        }
                        
                elif delta < 0:
                    total_sell_value += order_value
                    
                    if symbol in positions_dict:
                        old_qty = positions_dict[symbol]['quantity']
                        new_qty = old_qty + delta
                        
                        if new_qty <= 0:
                            del positions_dict[symbol]
                        else:
                            positions_dict[symbol]['quantity'] = new_qty
                            positions_dict[symbol]['market_value'] = new_qty * price
                            positions_dict[symbol]['price'] = price
            
            new_cash_balance = cash_balance - total_buy_value + total_sell_value
            new_positions = list(positions_dict.values())
            total_market_value = sum(p.get('market_value', 0) for p in new_positions)
            new_liquidation_value = new_cash_balance + total_market_value
            
            client_data['positions'] = new_positions
            client_data['positions_count'] = len(new_positions)
            client_data['balances']['cash_balance'] = round(new_cash_balance, 2)
            client_data['balances']['liquidation_value'] = round(new_liquidation_value, 2)
            client_data['balances']['available_funds'] = round(new_cash_balance, 2)
            client_data['total_pl'] = 0
            
            dry_cache['clients'][client_id] = client_data
            update_simulation_cache(dry_cache)
            
            logger.info(f"[SIMULATION] Dry cache updated: {len(new_positions)} positions, "
                        f"cash=${new_cash_balance:,.0f}")
            
        except Exception as e:
            logger.error(f"[SIMULATION] Failed to update dry cache: {e}")

    @staticmethod
    def _simulate_live_orders(
            deltas: Dict[str, int],
            prices: Dict[str, float]
    ) -> List[Dict]:
        """Симуляция LIVE ордеров (SIMULATION MODE)"""
        logger.info(f"[ORDER] 🔶 SIMULATION: {len(deltas)} virtual orders")

        results = []
        orders_summary = []
        total_buy = 0
        total_sell = 0

        for symbol, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            quantity = abs(delta)
            price = prices.get(symbol, 0)
            value = quantity * price

            if delta > 0:
                total_buy += value
            else:
                total_sell += value

            sim_order_id = f"SIM-{datetime.now().strftime('%H%M%S')}-{symbol}"

            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'status': 'SIMULATED',
                'order_id': sim_order_id,
                'timestamp': datetime.now().isoformat()
            })

            orders_summary.append(f"{action} {quantity} {symbol}")

        logger.info(f"🔶 SIMULATION: {', '.join(orders_summary)} | Net: ${total_buy - total_sell:,.0f}")

        return results

    @staticmethod
    def _dry_run_orders(
            deltas: Dict[str, int],
            prices: Dict[str, float]
    ) -> List[Dict]:
        """Симуляция ордеров (DRY RUN)"""
        logger.info(f"[ORDER] 🧪 DRY RUN: {len(deltas)} orders (not executed)")

        results = []

        for symbol, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            quantity = abs(delta)

            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': prices.get(symbol, 0),
                'status': 'DRY_RUN',
                'timestamp': datetime.now().isoformat()
            })

            logger.info(f"[ORDER]    🧪 {action} {quantity} {symbol} @ ${prices.get(symbol, 0):.2f}")

        return results

    def _build_result(
            self,
            scale: float,
            main_equity: float,
            slave_equity: float,
            deltas: Dict,
            valid_deltas: Dict,
            results: List,
            status: str,
            errors: List = None
    ) -> Dict:
        """Собрать результат синхронизации"""
        return {
            'timestamp': datetime.now().isoformat(),
            'status': status,
            'operating_mode': self.operating_mode,
            'scale': scale,
            'main_equity': main_equity,
            'slave_equity': slave_equity,
            'deltas': deltas,
            'valid_deltas': valid_deltas,
            'results': results,
            'errors': errors or [],
            'summary': {
                'total_deltas': len(deltas),
                'orders_placed': len(results),
                'orders_success': sum(1 for r in results if r.get('status') in ['SUCCESS', 'DRY_RUN', 'SIMULATED']),
                'orders_failed': sum(1 for r in results if r.get('status') == 'ERROR')
            }
        }

    def _get_history_file(self) -> str:
        """Получить путь к файлу истории в зависимости от режима"""
        base_file = self.config.get('history_file', 'data/sync_history.json')
        
        if self.operating_mode in ('dry_run', 'simulation'):
            if base_file.endswith('.json'):
                return base_file.replace('.json', '_dry.json')
            else:
                return base_file + '_dry'
        
        return base_file

    def _save_sync_result(self, result: Dict):
        """Сохранить результат синхронизации"""
        from app.core.json_utils import load_json, save_json
        from datetime import datetime, timedelta
        
        if self.operating_mode == 'live':
            orders = result.get('orders', [])
            if not orders:
                logger.info("[SYNC] 📝 History write skipped (LIVE: no orders executed)")
                return
        
        history_file = self._get_history_file()

        try:
            history = load_json(history_file, default=[])
            history.append(result)
            
            # Удалить записи старше 6 месяцев
            six_months_ago = datetime.now() - timedelta(days=180)
            history = [
                entry for entry in history
                if self._parse_timestamp(entry.get('timestamp', '')) > six_months_ago
            ]
            
            save_json(history_file, history)
            
            if self.operating_mode == 'live':
                import re
                match = re.search(r'data/clients/(.+)_history\.json', history_file)
                if match:
                    client_id = match.group(1)
                    ConfigCache.update_history(client_id, history)
            
            mode_str = self.operating_mode.upper()
            logger.info(f"[SYNC] 💾 Results saved to {history_file} ({mode_str})")
            
        except Exception as e:
            logger.error(f"❌ Failed to save results: {e}")
    
    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> datetime:
        """Парсить timestamp из истории"""
        from datetime import datetime
        try:
            # Попробовать разные форматы
            if 'T' in timestamp_str:
                # ISO формат: 2026-01-22T09:51:54.653783
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.min
        except Exception:
            return datetime.min

    def _update_cache_after_sync(
            self,
            main_positions: List,
            slave_positions: List,
            main_equity: float,
            slave_equity: float
    ):
        """Обновить account_cache.json после синхронизации"""
        from app.core.json_utils import load_json, save_json
        from app.core.paths import DATA_DIR
        
        try:
            cache_file = DATA_DIR / "account_cache.json"
            cache = load_json(str(cache_file), default={})
            
            if cache.get('main_account'):
                cache['main_account']['positions'] = [
                    {
                        'symbol': p.symbol,
                        'quantity': p.quantity,
                        'market_value': getattr(p, 'market_value', 0),
                        'unrealized_pl': getattr(p, 'unrealized_pl', 0)
                    }
                    for p in main_positions
                ]
                cache['main_account']['positions_count'] = len(main_positions)
                cache['main_account']['balances']['liquidation_value'] = main_equity
            
            client_id = self.config.get('client_id')
            if client_id and cache.get('clients', {}).get(client_id):
                cache['clients'][client_id]['positions'] = [
                    {
                        'symbol': p.symbol,
                        'quantity': p.quantity,
                        'market_value': getattr(p, 'market_value', 0),
                        'unrealized_pl': getattr(p, 'unrealized_pl', 0)
                    }
                    for p in slave_positions
                ]
                cache['clients'][client_id]['positions_count'] = len(slave_positions)
                cache['clients'][client_id]['balances']['liquidation_value'] = slave_equity
            
            cache['last_updated'] = datetime.now().isoformat()
            save_json(str(cache_file), cache)
            
            from app.core.cache_manager import set_cache_updated
            set_cache_updated(True)
            
            logger.debug(f"[SYNC] Cache updated after sync")
            
        except Exception as e:
            logger.warning(f"[SYNC] Could not update cache after sync: {e}")
