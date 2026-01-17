# app/modes/simulation/sync.py
"""
🔶 SIMULATION MODE - Виртуальные ордера с dry cache.

TODO: Реализовать полную логику:
- При Start: если Main имеет позиции → обнулить у клиентов
- При Start: если Main НЕ имеет позиций → создать фейковые позиции
- Дельта всегда ≠ 0 при первой итерации
"""

from typing import Dict, List
import schwabdev

from app.core.logger import logger
from app.modes.base import SyncMode


class SimulationSync(SyncMode):
    """
    🔶 SIMULATION MODE - Виртуальные ордера с dry cache.
    
    ЗАГЛУШКА - логика будет реализована позже.
    
    Особенности (планируемые):
    - Использует account_cache_dry.json для хранения виртуальных позиций
    - НЕ отправляет реальные ордера
    - Обновляет dry cache после каждой синхронизации
    - История сохраняется в {client_id}_history_dry.json
    """
    
    MODE_ICON = "🔶"
    MODE_NAME = "SIMULATION"
    
    def __init__(self, main_client: schwabdev.Client, slave_client: schwabdev.Client, config: Dict):
        super().__init__(main_client, slave_client, config)
        # TODO: Добавить calculator, validator
    
    def sync(
        self,
        main_account_hash: str,
        slave_account_hash: str,
        skip_history: bool = False
    ) -> Dict:
        """
        Выполнить SIMULATION синхронизацию.
        
        ЗАГЛУШКА - вернуть пустой результат.
        
        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта
            skip_history: Пропустить запись в историю
            
        Returns:
            Результаты синхронизации
        """
        self.log_start()
        
        logger.warning(f"{self.MODE_ICON} SIMULATION sync not implemented yet!")
        logger.warning("Please use the old synchronizer.py for now")
        
        # Логировать завершение
        logger.info(f"{'═' * 50}")
        logger.info(f"{self.MODE_ICON} {self.MODE_NAME} (STUB) done")
        
        return {
            'status': 'NOT_IMPLEMENTED',
            'operating_mode': 'simulation',
            'message': 'Simulation sync not yet migrated to new modes/ structure'
        }
