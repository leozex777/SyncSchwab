# app/modes/live/sync.py
"""
🔴 LIVE MODE - Синхронизация с реальными ордерами.
"""

from typing import Dict
import schwabdev

from app.core.logger import logger
from app.core.sync_common import (
    InvalidAccountHashError,
    get_notification_settings,
    get_positions,
    get_equity,
    get_available_cash,
    get_prices,
    build_sync_result,
    save_sync_result,
    update_account_cache_after_sync
)
from app.core.notification_service import get_notification_service
from app.models.copier.calculator import PositionCalculator
from app.models.copier.validator import OrderValidator
from app.modes.base import SyncMode
from app.modes.live.orders import execute_orders


class LiveSync(SyncMode):
    """
    🔴 LIVE MODE - Синхронизация с реальными ордерами.
    
    Особенности:
    - Отправляет реальные ордера на Schwab API
    - Использует реальные данные из API (не dry cache)
    - История сохраняется в {client_id}_history.json
    """
    
    MODE_ICON = "🔴"
    MODE_NAME = "LIVE"
    
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
        Выполнить LIVE синхронизацию.
        
        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта
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
            # 1. Получить позиции из API
            main_positions = get_positions(self.main_client, main_account_hash, "Main")
            slave_positions = get_positions(self.slave_client, slave_account_hash, "Slave")
            
            # 2. Получить equity из API
            main_equity = get_equity(self.main_client, main_account_hash, "Main")
            slave_equity = get_equity(self.slave_client, slave_account_hash, "Slave")
            
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
                return build_sync_result(
                    operating_mode='live',
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
            
            # 6. Получить доступные средства
            available_cash = get_available_cash(
                self.slave_client,
                slave_account_hash,
                self.config
            )
            
            # 7. Валидировать ордера
            valid_deltas, errors = self.validator.validate_all_orders(
                deltas,
                prices,
                available_cash
            )
            
            # 8. Выполнить РЕАЛЬНЫЕ ордера
            results = []
            if valid_deltas:
                logger.info("🔴 LIVE MODE: Executing real orders!")
                results = execute_orders(
                    self.slave_client,
                    slave_account_hash,
                    valid_deltas,
                    prices
                )
            
            # 9. Сформировать результат
            sync_result = build_sync_result(
                operating_mode='live',
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
                save_sync_result(sync_result, self.client_id, 'live')
            else:
                logger.debug("History write skipped")
            
            # 11. Обновить кэш после sync
            update_account_cache_after_sync(
                self.client_id,
                main_positions,
                slave_positions,
                main_equity,
                slave_equity
            )
            
            # Логировать завершение
            self.log_complete(len(results), scale)
            
            return sync_result
            
        except InvalidAccountHashError:
            raise
        except Exception as e:
            logger.error(f"❌ LIVE Sync failed: {e}")
            raise
