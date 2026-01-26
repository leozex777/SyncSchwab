# app/modes/base.py
"""
Базовый класс для всех режимов синхронизации.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from app.core.logger import logger


class SyncMode(ABC):
    """
    Абстрактный базовый класс для режимов синхронизации.
    
    Каждый режим наследует этот класс и реализует свою логику.
    """
    
    # Иконка и название режима (переопределяются в наследниках)
    MODE_ICON = "❓"
    MODE_NAME = "UNKNOWN"
    
    def __init__(self, main_client, slave_client, config: Dict):
        """
        Args:
            main_client: schwabdev.Client для Main Account
            slave_client: schwabdev.Client для Slave Account
            config: Конфигурация клиента (settings + client_id)
        """
        self.main_client = main_client
        self.slave_client = slave_client
        self.config = config
        self.client_id = config.get('client_id', 'unknown')
    
    @abstractmethod
    def sync(
        self,
        main_account_hash: str,
        slave_account_hash: str,
        skip_history: bool = False
    ) -> Dict:
        """
        Выполнить синхронизацию.
        
        Args:
            main_account_hash: Hash главного аккаунта
            slave_account_hash: Hash клиентского аккаунта
            skip_history: Пропустить запись в историю
            
        Returns:
            Результаты синхронизации
        """
        pass
    
    def log_start(self):
        """Логировать начало синхронизации"""
        logger.debug(f"{self.MODE_ICON} {self.MODE_NAME} sync started for {self.client_id}")
    
    def log_complete(self, orders_count: int, scale: float):
        """Логировать завершение синхронизации"""
        logger.info(f"{'═' * 50}")
        logger.info(f"{self.MODE_ICON} {self.MODE_NAME} done | {orders_count} orders | Scale {scale*100:.1f}%")
