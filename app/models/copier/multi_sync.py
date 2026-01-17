
# multi_sync.py
# app.models.copier.multi_sync

from typing import List, Dict, Optional
from app.models.clients.client_manager import ClientManager
from app.models.copier.synchronizer import PositionSynchronizer, InvalidAccountHashError
from app.core.config import build_client_for_slave, get_hash_account
from app.gui.utils.env_manager import load_client_from_env
from app.core.logger import logger
from app.core.config_cache import ConfigCache


def get_operating_mode() -> str:
    """
    Получить текущий operating_mode из general_settings.json (через кэш)
    
    Returns:
        'monitor', 'simulation', или 'live'
    """
    settings = ConfigCache.get_general_settings()
    return settings.get('operating_mode', 'monitor')


def is_monitor_mode() -> bool:
    """
    Проверить находимся ли в режиме MONITOR
    
    Returns:
        True если monitor
    """
    return get_operating_mode() == 'monitor'


def is_simulation_mode() -> bool:
    """
    Проверить находимся ли в режиме SIMULATION
    
    Returns:
        True если simulation
    """
    return get_operating_mode() == 'simulation'


def is_live_mode() -> bool:
    """
    Проверить находимся ли в режиме LIVE
    
    Returns:
        True если live
    """
    return get_operating_mode() == 'live'


class MultiSynchronizer:
    """Синхронизация нескольких slave аккаунтов"""

    def __init__(self, main_client, client_manager: ClientManager, operating_mode: str = None):
        """
        Args:
            main_client: schwabdev.Client для Main Account
            client_manager: Менеджер клиентов
            operating_mode: Режим работы (None = читать из general_settings.json)
                           Значения: 'dry_run', 'simulation', 'live'
        """
        self.main_client = main_client
        self.client_manager = client_manager
        
        # Если режим не указан явно — читать из настроек
        if operating_mode is None:
            self.operating_mode = get_operating_mode()
        else:
            self.operating_mode = operating_mode
        
        # Логировать режим при инициализации
        mode_icons = {
            'monitor': "MONITOR 🔍",
            'simulation': "SIMULATION 🔶",
            'live': "LIVE 🔴"
        }
        mode_str = mode_icons.get(self.operating_mode, "UNKNOWN")
        logger.debug(f"MultiSynchronizer: {mode_str} mode")

    def sync_all(self, selected_clients: List[str] = None, skip_history: bool = False) -> Dict:
        """
        Синхронизировать всех клиентов

        Args:
            selected_clients: Список ID клиентов (None = все активные)
            skip_history: Пропустить запись в историю (для повторных Auto Sync DRY RUN)

        Returns:
            Результаты по каждому клиенту
        """
        # Получить главный аккаунт hash
        main_hash = self.client_manager.main_account.get('account_hash')

        if not main_hash:
            logger.error("❌ Main account hash not found")
            return {'error': 'Main account not configured'}

        # Получить клиентов для синхронизации
        if selected_clients:
            clients = [self.client_manager.get_client(cid) for cid in selected_clients]
            clients = [c for c in clients if c and c.enabled]
        else:
            clients = self.client_manager.get_enabled_clients()

        # Логировать режим
        mode_icons = {
            'monitor': "🔍 MONITOR",
            'simulation': "🔶 SIMULATION",
            'live': "🔴 LIVE"
        }
        mode_str = mode_icons.get(self.operating_mode, "UNKNOWN")
        
        logger.debug(f"Multi-sync: {len(clients)} clients ({mode_str})")

        results = {}

        for client_config in clients:
            logger.debug(f"Syncing {client_config.name}")

            try:
                # Загрузить credentials клиента
                env_data = load_client_from_env(client_config.id)

                if not env_data or not env_data.get('key_id'):
                    raise ValueError(f"Credentials not found for {client_config.id}")

                # Создать client для этого slave
                slave_client = build_client_for_slave(
                    client_config.id,
                    env_data['key_id'],
                    env_data['client_secret'],
                    env_data['redirect_uri']
                )

                # Получить hash slave аккаунта
                slave_hash = client_config.account_hash

                # Создать config с client_id для SIMULATION
                sync_config = {**client_config.settings, 'client_id': client_config.id}

                # Создать синхронизатор для клиента
                synchronizer = PositionSynchronizer(
                    main_client=self.main_client,
                    slave_client=slave_client,
                    config=sync_config,
                    operating_mode=self.operating_mode  # Передаем режим
                )

                # Синхронизировать (с обработкой ошибки hash)
                try:
                    result = synchronizer.sync(main_hash, slave_hash, skip_history=skip_history)
                    
                except InvalidAccountHashError as hash_error:
                    logger.warning(f"⚠️ Invalid hash detected, attempting to refresh...")
                    
                    # Попытка обновить hash и повторить
                    updated = self._refresh_account_hashes(slave_client, client_config)
                    
                    if updated:
                        # Получить обновленные hash
                        main_hash = self.client_manager.main_account.get('account_hash')
                        slave_hash = client_config.account_hash
                        
                        # Повторить синхронизацию
                        result = synchronizer.sync(main_hash, slave_hash, skip_history=skip_history)
                    else:
                        raise hash_error

                # Сохранить результат
                results[client_config.id] = {
                    'status': 'success',
                    'client_name': client_config.name,
                    'result': result
                }

                logger.debug(f"✅ {client_config.name} synced")

            except InvalidAccountHashError as e:
                logger.error(f"❌ Invalid account hash for {client_config.name}: {e}")
                results[client_config.id] = {
                    'status': 'error',
                    'client_name': client_config.name,
                    'error': f"Invalid account hash: {e}"
                }

            except Exception as e:
                logger.error(f"❌ Error syncing {client_config.name}: {e}")
                results[client_config.id] = {
                    'status': 'error',
                    'client_name': client_config.name,
                    'error': str(e)
                }

        logger.debug(f"Multi-sync complete: {len(results)} clients")
        return results

    def _refresh_account_hashes(self, slave_client, client_config) -> bool:
        """
        Обновить account_hash для main и slave аккаунтов

        Returns:
            True если обновление успешно
        """
        import os
        updated = False

        try:
            # Обновить Main Account hash
            main_account_number = os.getenv('MAIN_ACCOUNT_NUMBER')
            if main_account_number:
                new_main_hash = get_hash_account(self.main_client, main_account_number)
                if new_main_hash:
                    self.client_manager.set_main_account(new_main_hash, main_account_number)
                    logger.info(f"✅ Main account hash updated: {new_main_hash[:8]}...")
                    updated = True

            # Обновить Slave Account hash
            slave_account_number = client_config.account_number
            if slave_account_number:
                new_slave_hash = get_hash_account(slave_client, slave_account_number)
                if new_slave_hash:
                    self.client_manager.update_client(
                        client_config.id,
                        {'account_hash': new_slave_hash}
                    )
                    # Обновить локальный объект
                    client_config.account_hash = new_slave_hash
                    logger.info(f"✅ Slave account hash updated: {new_slave_hash[:8]}...")
                    updated = True

        except (AttributeError, KeyError, ValueError) as e:
            logger.error(f"❌ Failed to refresh account hashes: {e}")

        return updated

    def sync_one(self, client_id: str) -> Dict:
        """
        Синхронизировать одного клиента

        Args:
            client_id: ID клиента для синхронизации

        Returns:
            Результат синхронизации
        """
        return self.sync_all(selected_clients=[client_id])

    def calculate_delta_for_client(self, client_config) -> Optional[Dict]:
        """
        Рассчитать дельту для одного клиента (без выполнения ордеров).
        
        Используется в Monitor режиме для отслеживания изменений.
        
        Args:
            client_config: Конфигурация клиента
            
        Returns:
            {
                'deltas': {symbol: quantity},
                'prices': {symbol: price},
                'total_estimated': float
            }
            или None при ошибке
        """
        from app.models.copier.calculator import PositionCalculator
        from app.models.copier.entities import parse_positions_from_account_details
        
        try:
            # Получить главный аккаунт hash
            main_hash = self.client_manager.main_account.get('account_hash')
            if not main_hash:
                logger.error("[MONITOR] Main account hash not found")
                return None
            
            # Загрузить credentials клиента
            env_data = load_client_from_env(client_config.id)
            if not env_data or not env_data.get('key_id'):
                logger.error(f"[MONITOR] Credentials not found for {client_config.id}")
                return None
            
            # Создать client для этого slave
            slave_client = build_client_for_slave(
                client_config.id,
                env_data['key_id'],
                env_data['client_secret'],
                env_data['redirect_uri']
            )
            
            # Получить hash slave аккаунта
            slave_hash = client_config.account_hash
            
            # Получить позиции Main
            main_response = self.main_client.account_details(main_hash, fields='positions')
            main_details = main_response.json()
            main_positions = parse_positions_from_account_details(main_details)
            
            # Получить позиции Slave
            slave_response = slave_client.account_details(slave_hash, fields='positions')
            slave_details = slave_response.json()
            slave_positions = parse_positions_from_account_details(slave_details)
            
            # Получить equity для расчёта scale
            main_equity = (main_details.get('securitiesAccount', {}).get('currentBalances', {})
                           .get('liquidationValue', 0))
            slave_equity = (slave_details.get('securitiesAccount', {}).get('currentBalances', {})
                            .get('liquidationValue', 0))
            
            # Создать calculator
            calculator = PositionCalculator(
                threshold=client_config.settings.get('threshold', 0.03)
            )
            
            # Рассчитать scale
            scale = calculator.calculate_scale(
                main_equity,
                slave_equity,
                method=client_config.settings.get('scale_method', 'DYNAMIC_RATIO'),
                fixed_amount=client_config.settings.get('fixed_amount')
            )
            
            # Рассчитать дельты
            deltas_dict = calculator.calculate_all_deltas(
                main_positions,
                slave_positions,
                scale,
                rounding_method=client_config.settings.get('rounding_method', 'ROUND_DOWN')
            )
            
            if not deltas_dict:
                return {
                    'deltas': {},
                    'prices': {},
                    'total_estimated': 0
                }
            
            # Получить цены из позиций
            prices = {}
            for pos in main_positions:
                prices[pos.symbol] = pos.average_price
            
            # Рассчитать total estimated
            total_estimated = sum(
                abs(qty) * prices.get(symbol, 0)
                for symbol, qty in deltas_dict.items()
            )
            
            logger.debug(f"[MONITOR] Delta calculated for {client_config.id}: {len(deltas_dict)} symbols")
            
            return {
                'deltas': deltas_dict,
                'prices': prices,
                'total_estimated': total_estimated
            }
            
        except Exception as e:
            logger.error(f"[MONITOR] Error calculating delta for {client_config.id}: {e}")
            return None
