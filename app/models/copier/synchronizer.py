
# synchronizer.py
# app.models.copier.synchronizer

from typing import Dict, List, Optional
import schwabdev
from datetime import datetime
from app.models.copier.calculator import PositionCalculator
from app.models.copier.validator import OrderValidator
from app.models.copier.entities import parse_positions_from_account_details
from app.core.logger import logger
from app.core.json_utils import save_json, load_json
from app.core.config_cache import ConfigCache
from app.core.notification_service import get_notification_service


def get_notification_settings() -> dict:
    """Получить настройки уведомлений из конфига (через кэш)"""
    settings = ConfigCache.get_general_settings()
    notifications = settings.get('notifications', {})
    
    return {
        'toast_on_error': notifications.get('toast_on_error', True),
        'toast_on_success': notifications.get('toast_on_success', False),
        'sound_on_error': notifications.get('sound_on_error', True),
        'telegram_enabled': notifications.get('telegram_enabled', False),
        'telegram_bot_token': notifications.get('telegram_bot_token', ''),
        'telegram_chat_id': notifications.get('telegram_chat_id', '')
    }


def _play_error_sound():
    """Воспроизвести звук ошибки"""
    try:
        import platform
        if platform.system() == 'Windows':
            import winsound
            # Системный звук ошибки
            winsound.MessageBeep(winsound.MB_ICONHAND)
        else:
            # Linux/Mac - использовать bell
            print('\a', end='', flush=True)
    except Exception as e:
        logger.debug(f"Could not play error sound: {e}")


class InvalidAccountHashError(Exception):
    """Ошибка невалидного account_hash"""
    pass


class PositionSynchronizer:
    """Синхронизатор позиций между аккаунтами"""

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

        self.calculator = PositionCalculator(
            threshold=config.get('threshold', 0.03)
        )

        self.validator = OrderValidator(config)

    def sync(
            self,
            main_account_hash: str,
            slave_account_hash: str,
            skip_history: bool = False
    ) -> Dict:
        """
        Выполнить синхронизацию

        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта
            skip_history: Пропустить запись в историю (для повторных Auto Sync DRY RUN)

        Returns:
            Результаты синхронизации
        """
        mode_icons = {
            'dry_run': ('🧪', 'DRY RUN'),
            'simulation': ('🔶', 'SIMULATION'),
            'live': ('🔴', 'LIVE')
        }
        mode_icon, mode_str = mode_icons.get(self.operating_mode, ('❓', 'UNKNOWN'))
        
        # Получить настройки уведомлений
        notif_settings = get_notification_settings()
        notif = get_notification_service()
        
        # Уведомление о начале (только если toast_on_success включен)
        if notif_settings['toast_on_success']:
            notif.info(f"{mode_icon} Sync started ({mode_str})")
        
        logger.info("[SYNC] " + "=" * 55)
        logger.info(f"[SYNC] {mode_icon} Starting synchronization")
        logger.info(f"[SYNC]    Mode: {mode_str}")
        if self.operating_mode == 'simulation':
            logger.info(f"[SYNC]    ⚠️ SIMULATION: Orders will NOT be sent to Schwab")
        logger.info("[SYNC] " + "=" * 55)

        try:
            # 1. Получить позиции
            main_positions = self._get_positions(self.main_client, main_account_hash, "Main")
            slave_positions = self._get_positions(self.slave_client, slave_account_hash, "Slave")

            # 2. Получить equity
            main_equity = self._get_equity(self.main_client, main_account_hash, "Main")
            slave_equity = self._get_equity(self.slave_client, slave_account_hash, "Slave")

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
                logger.info("[SYNC] ✅ All positions are in sync, no orders needed")
                return self._build_result(
                    scale, main_equity, slave_equity,
                    deltas, {}, [], "SUCCESS"
                )

            # 5. Получить цены
            prices = self._get_prices(main_positions)

            # 6. Получить доступные средства
            available_cash = self._get_available_cash(self.slave_client, slave_account_hash)

            # 7. Валидировать ордера
            valid_deltas, errors = self.validator.validate_all_orders(
                deltas,
                prices,
                available_cash
            )

            # 8. Выполнить ордера
            if self.operating_mode == 'live' and valid_deltas:
                # LIVE MODE - реальные ордера
                logger.info("🔴 LIVE MODE: Executing real orders!")
                results = self._execute_orders(
                    self.slave_client,
                    slave_account_hash,
                    valid_deltas,
                    prices
                )
            elif self.operating_mode == 'simulation' and valid_deltas:
                # SIMULATION - всё как Live, но без отправки
                logger.info("🔶 SIMULATION: Showing what would be executed...")
                results = self._simulate_live_orders(valid_deltas, prices)
            else:
                # DRY RUN - быстрая симуляция
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

            # Сохранить в историю (если не пропускаем)
            if not skip_history:
                self._save_sync_result(sync_result)
            else:
                logger.info("📝 History write skipped (Auto Sync DRY RUN iteration)")

            logger.info("[SYNC] " + "=" * 55)
            logger.info(f"[SYNC] ✅ Synchronization complete: {len(results)} orders")
            logger.info("[SYNC] " + "=" * 55)
            
            # ═══════════════════════════════════════════════════════════════
            # ОБНОВИТЬ КЭШ ПОСЛЕ SYNC (для GUI)
            # ═══════════════════════════════════════════════════════════════
            self._update_cache_after_sync(main_positions, slave_positions, main_equity, slave_equity)
            
            # Уведомление о завершении
            success_count = sum(1 for r in results if r.get('status') in ['SUCCESS', 'DRY_RUN', 'SIMULATED'])
            error_count = sum(1 for r in results if r.get('status') == 'ERROR')
            
            # Toast при ошибках (если включено)
            if error_count > 0 and notif_settings['toast_on_error']:
                notif.sync_completed(success_count, error_count)
            # Toast при успехе (если включено)
            elif error_count == 0 and notif_settings['toast_on_success']:
                notif.sync_completed(success_count, error_count)

            return sync_result

        except InvalidAccountHashError:
            # Пробросить ошибку выше для обработки в multi_sync
            raise

        except Exception as e:
            logger.error(f"❌ Synchronization failed: {e}")
            raise

    def _get_positions(
            self,
            client: schwabdev.Client,
            account_hash: str,
            label: str
    ) -> List:
        """Получить позиции аккаунта"""
        logger.info(f"📥 Getting {label} positions...")

        try:
            response = client.account_details(account_hash, fields='positions')
            
            # Проверить на ошибку invalid hash
            if self._is_invalid_hash_error(response):
                logger.error(f"❌ Invalid account hash for {label}: {account_hash[:8]}...")
                raise InvalidAccountHashError(f"Invalid account hash for {label}")
            
            details = response.json()
            positions = parse_positions_from_account_details(details)

            logger.info(f"   {label}: {len(positions)} positions")
            return positions
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            # Проверить текст ошибки на invalid hash
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
            
            # Проверить на ошибку invalid hash
            if self._is_invalid_hash_error(response):
                raise InvalidAccountHashError(f"Invalid account hash for {label}")
            
            details = response.json()
            sa = details.get('securitiesAccount', {})
            equity = sa.get('currentBalances', {}).get('liquidationValue', 0)

            logger.info(f"   {label} Equity: ${equity:,.2f}")
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
        """
        Получить доступные средства с учетом настроек маржи.
        
        Логика:
        1. Если buyingPower = 0 → использовать cashBalance
        2. Если buyingPower > 0 и use_margin = False → cashBalance
        3. Если buyingPower > 0 и use_margin = True:
           - user_limit = totalValue * (1 + margin_percent/100)
           - max_allowed = min(buyingPower, user_limit)
           - available = max(0, max_allowed - positions_value)
        """
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
            
            # Рассчитать positions_value
            positions = sa.get('positions', [])
            positions_value = sum(
                p.get('marketValue', 0) 
                for p in positions
            )
            
            # Логирование исходных данных
            logger.info(f"   Total Value: ${total_value:,.2f}")
            logger.info(f"   Positions Value: ${positions_value:,.2f}")
            logger.info(f"   Cash Balance: ${cash_balance:,.2f}")
            logger.info(f"   Buying Power (API): ${buying_power:,.2f}")
            
            # ═══════════════════════════════════════════════════════════
            # СЛУЧАЙ 1: buyingPower = 0 (Cash Account без маржи)
            # ═══════════════════════════════════════════════════════════
            if buying_power == 0:
                available = cash_balance
                logger.info(f"   buyingPower=0, using cashBalance")
                logger.info(f"   Available for trading: ${available:,.2f}")
                return available
            
            # ═══════════════════════════════════════════════════════════
            # СЛУЧАЙ 2: buyingPower > 0
            # ═══════════════════════════════════════════════════════════
            
            # Получить настройки маржи из config
            use_margin = self.config.get('use_margin', False)
            margin_percent = self.config.get('margin_percent', 0)
            
            # Проверить разрешение маржи от Schwab
            schwab_allows_margin = buying_power > cash_balance * 1.1
            
            if not use_margin:
                # ═══════════════════════════════════════════════════════
                # Маржа ВЫКЛЮЧЕНА пользователем → только cashBalance
                # ═══════════════════════════════════════════════════════
                available = cash_balance
                logger.info(f"   Margin disabled by user, using cashBalance")
            
            elif use_margin and not schwab_allows_margin:
                # ═══════════════════════════════════════════════════════
                # Маржа ВКЛЮЧЕНА, но Schwab НЕ разрешает
                # ═══════════════════════════════════════════════════════
                available = cash_balance
                logger.warning(f"   Margin requested but NOT available from Schwab")
            
            elif use_margin and schwab_allows_margin and margin_percent > 0:
                # ═══════════════════════════════════════════════════════
                # Маржа ВКЛЮЧЕНА и Schwab РАЗРЕШАЕТ
                # ═══════════════════════════════════════════════════════
                
                # Лимит пользователя: Total Value + margin_percent%
                user_limit = total_value * (1 + margin_percent / 100)
                
                # Ограничить тем что даёт Schwab
                max_allowed = min(buying_power, user_limit)
                
                # Доступно = лимит - уже открытые позиции
                available = max(0, max_allowed - positions_value)
                
                logger.info(f"   Margin enabled: {margin_percent}% buffer")
                logger.info(f"   User limit: ${user_limit:,.2f}")
                logger.info(f"   Max allowed: ${max_allowed:,.2f} (min of buyingPower and user_limit)")
            
            else:
                # Fallback
                available = cash_balance
            
            logger.info(f"   Available for trading: ${available:,.2f}")
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
            # Проверить HTTP статус
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

    @staticmethod
    def _get_prices(positions: List) -> Dict[str, float]:
        """Получить цены из позиций"""
        prices = {}
        for pos in positions:
            prices[pos.symbol] = pos.average_price
        return prices

    def _execute_orders(
            self,
            client: schwabdev.Client,
            account_hash: str,
            deltas: Dict[str, int],
            prices: Dict[str, float]
    ) -> List[Dict]:
        """Выполнить реальные ордера (LIVE MODE) с обработкой ошибок"""
        from app.core.error_handler import (
            RetryHandler, ErrorTracker, get_error_settings
        )
        
        logger.info(f"[ORDER] 🔴 Executing {len(deltas)} LIVE orders...")
        
        # Получить настройки
        error_settings = get_error_settings()
        retry_handler = RetryHandler(max_retries=error_settings['retry_count'])
        error_tracker = ErrorTracker(max_errors=error_settings['max_errors_per_session'])
        
        results = []

        for symbol, delta in deltas.items():
            # Проверить нужно ли остановиться
            if error_tracker.should_stop(error_settings['stop_on_critical']):
                logger.error(f"🛑 Stopping order execution due to critical errors")
                # Добавить оставшиеся ордера как пропущенные
                remaining = {k: v for k, v in deltas.items() if k not in [r['symbol'] for r in results]}
                for sym, d in remaining.items():
                    results.append({
                        'symbol': sym,
                        'action': "BUY" if d > 0 else "SELL",
                        'quantity': abs(d),
                        'price': prices.get(sym, 0),
                        'status': 'SKIPPED',
                        'error': 'Stopped due to critical errors',
                        'timestamp': datetime.now().isoformat()
                    })
                break
            
            # Определить action и quantity
            action = "BUY" if delta > 0 else "SELL"
            quantity = abs(delta)

            # Функция для отправки ордера
            def place_order():
                if action == "BUY":
                    from schwab.orders.equities import equity_buy_market
                    order = equity_buy_market(symbol, quantity).build()
                else:
                    from schwab.orders.equities import equity_sell_market
                    order = equity_sell_market(symbol, quantity).build()
                return client.order_place(account_hash, order)

            # Выполнить с retry
            response, api_error = retry_handler.execute_with_retry(
                place_order,
                symbol=symbol
            )

            if api_error is None:
                # Успех
                order_id = self._extract_order_id(response)
                error_tracker.add_success()
                
                results.append({
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': prices.get(symbol, 0),
                    'status': 'SUCCESS',
                    'order_id': order_id,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"[ORDER]    🔴 ✅ {action} {quantity} {symbol} @ "
                            f"${prices.get(symbol, 0):.2f} (Order ID: {order_id})")
                
                # Toast уведомление (если toast_on_success включен)
                notif_settings = get_notification_settings()
                if notif_settings['toast_on_success']:
                    notif = get_notification_service()
                    notif.order_success(symbol, action, quantity)
            else:
                # Ошибка
                error_tracker.add_error(api_error)
                
                results.append({
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': prices.get(symbol, 0),
                    'status': 'ERROR',
                    'error': api_error.message,
                    'error_type': api_error.error_type.value,
                    'error_code': api_error.code,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.error(f"[ORDER]    🔴 ❌ {action} {quantity} {symbol}: {api_error.message}")
                
                # Toast уведомление об ошибке (если toast_on_error включен)
                notif_settings = get_notification_settings()
                if notif_settings['toast_on_error']:
                    notif = get_notification_service()
                    notif.order_error(symbol, action, api_error.message)
                
                # Звук при ошибке (если sound_on_error включен)
                if notif_settings['sound_on_error']:
                    _play_error_sound()
        
        # Логировать сводку ошибок
        error_summary = error_tracker.get_summary()
        if error_summary['total_errors'] > 0:
            logger.warning(f"[ORDER] ⚠️ Order execution completed with {error_summary['total_errors']} errors")
        
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

    @staticmethod
    def _simulate_live_orders(
            deltas: Dict[str, int],
            prices: Dict[str, float]
    ) -> List[Dict]:
        """
        Live Simulation - показать что было бы отправлено, но без реальной отправки.
        Полезно для тестирования Live логики без риска.
        """
        logger.info(f"[ORDER] 🔶 LIVE SIMULATION: {len(deltas)} orders")
        logger.info("[ORDER] " + "=" * 45)
        logger.info("[ORDER] ⚠️  SIMULATION MODE - NO ORDERS SENT TO SCHWAB")
        logger.info("[ORDER] " + "=" * 45)

        results = []
        total_buy = 0
        total_sell = 0

        for symbol, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            quantity = abs(delta)
            price = prices.get(symbol, 0)
            value = quantity * price

            if action == "BUY":
                total_buy += value
            else:
                total_sell += value

            # Симулированный order_id
            sim_order_id = f"SIM-{symbol}-{datetime.now().strftime('%H%M%S')}"

            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'status': 'SIMULATED',
                'order_id': sim_order_id,
                'timestamp': datetime.now().isoformat()
            })

            logger.info(f"[ORDER]    🔶 Would {action} {quantity} {symbol} @ ${price:.2f} = ${value:,.2f}")
            logger.info(f"[ORDER]       Order ID: {sim_order_id}")
            logger.info(f"[ORDER]       ✅ Validated, ready to execute")

        logger.info("[ORDER] " + "=" * 45)
        logger.info(f"[ORDER] 📊 SIMULATION SUMMARY:")
        logger.info(f"[ORDER]    Total BUY:  ${total_buy:,.2f}")
        logger.info(f"[ORDER]    Total SELL: ${total_sell:,.2f}")
        logger.info(f"[ORDER]    Net:        ${total_buy - total_sell:,.2f}")
        logger.info("[ORDER] " + "=" * 45)
        logger.info("[ORDER] ⚠️  To execute real orders, disable simulation mode")

        return results

    @staticmethod
    def _extract_order_id(response) -> Optional[str]:
        """Извлечь order ID из ответа"""
        try:
            location = response.headers.get('Location', '')
            if '/orders/' in location:
                return location.split('/orders/')[-1]
        except AttributeError:
            pass
        except Exception as e:
            logger.warning(f"Could not extract order ID: {e}")
        return None

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
        """
        Получить путь к файлу истории в зависимости от режима.
        
        DRY RUN / SIMULATION: slave_1_history_dry.json
        LIVE: slave_1_history.json
        """
        base_file = self.config.get('history_file', 'data/sync_history.json')
        
        if self.operating_mode in ('dry_run', 'simulation'):
            # Добавить суффикс _dry перед .json
            if base_file.endswith('.json'):
                return base_file.replace('.json', '_dry.json')
            else:
                return base_file + '_dry'
        
        return base_file

    def _save_sync_result(self, result: Dict):
        """
        Сохранить результат синхронизации в соответствующий файл.
        
        LIVE Mode: записывать только если были реальные ордера
        DRY RUN / SIMULATION: записывать всегда (управляется skip_history)
        """
        # LIVE Mode: пропустить если не было ордеров
        if self.operating_mode == 'live':
            orders = result.get('orders', [])
            if not orders:
                logger.info("[SYNC] 📝 History write skipped (LIVE: no orders executed)")
                return
        
        history_file = self._get_history_file()

        try:
            history = load_json(history_file, default=[])
            history.append(result)
            
            if self.operating_mode in ('dry_run', 'simulation'):
                # DRY RUN / SIMULATION: ограничить до 50 записей
                if len(history) > 50:
                    history = history[-50:]
            # LIVE: хранить всё (архивация 1 января каждого года)
            
            save_json(history_file, history)
            
            # Обновить кэш для LIVE режима
            if self.operating_mode == 'live':
                # Извлечь client_id из history_file (формат: data/clients/{client_id}_history.json)
                import re
                match = re.search(r'data/clients/(.+)_history\.json', history_file)
                if match:
                    client_id = match.group(1)
                    ConfigCache.update_history(client_id, history)
            
            mode_str = self.operating_mode.upper()
            logger.info(f"[SYNC] 💾 Results saved to {history_file} ({mode_str})")
            
        except Exception as e:
            logger.error(f"❌ Failed to save results: {e}")

    def _update_cache_after_sync(
            self,
            main_positions: List,
            slave_positions: List,
            main_equity: float,
            slave_equity: float
    ):
        """
        Обновить account_cache.json после синхронизации.
        
        Использует данные уже полученные в sync() чтобы не делать
        дополнительных API вызовов.
        """
        from app.core.json_utils import load_json, save_json
        from app.core.paths import DATA_DIR
        from datetime import datetime
        
        try:
            cache_file = DATA_DIR / "account_cache.json"
            cache = load_json(str(cache_file), default={})
            
            # Обновить Main Account
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
                cache['main_account']['updated_at'] = datetime.now().isoformat()
            
            # Обновить Slave (текущий клиент)
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
                cache['clients'][client_id]['updated_at'] = datetime.now().isoformat()
            
            # Обновить общий timestamp
            cache['last_updated'] = datetime.now().isoformat()
            
            # Сохранить
            save_json(str(cache_file), cache)
            
            # Установить флаг для автообновления GUI
            from app.core.cache_manager import set_cache_updated
            set_cache_updated(True)
            
            logger.debug(f"[SYNC] Cache updated after sync")
            
        except Exception as e:
            logger.warning(f"[SYNC] Could not update cache after sync: {e}")
