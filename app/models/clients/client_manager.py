
# client_manager.py
# app.models.clients.client_manager

# app/models/clients/client_manager.py

from typing import List, Dict, Optional
from app.core.json_utils import save_json
from app.core.config_cache import ConfigCache


class ClientConfig:
    """Конфигурация одного клиента"""

    def __init__(self, data: Dict):
        self.id = data.get('id')
        self.account_hash = data.get('account_hash')
        self.account_number = data.get('account_number')
        self.name = data.get('name')
        self.enabled = data.get('enabled', True)
        self.settings = data.get('settings', {})

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'account_hash': self.account_hash,
            'account_number': self.account_number,
            'name': self.name,
            'enabled': self.enabled,
            'settings': self.settings
        }


class ClientManager:
    """Управление клиентами"""

    def __init__(self, config_file: str = 'config/clients.json'):
        self.config_file = config_file
        self.clients: List[ClientConfig] = []
        self.main_account: Dict = {}  # ← Инициализируем пустым словарем
        self.load_clients()

    def load_clients(self):
        """Загрузить клиентов из конфига (через кэш)"""
        data = ConfigCache.get_clients()
        
        # Если data - список (старый формат) или пустой - преобразовать
        if isinstance(data, list):
            data = {'main_account': {}, 'slave_accounts': data}

        self.main_account = data.get('main_account', {})  # ← Дефолт пустой словарь

        slave_data = data.get('slave_accounts', [])
        self.clients = [ClientConfig(client) for client in slave_data]

    def save_clients(self):
        """Сохранить клиентов в конфиг и обновить кэш"""
        data = {
            'main_account': self.main_account,
            'slave_accounts': [client.to_dict() for client in self.clients]
        }
        save_json(self.config_file, data)
        # Обновить кэш
        ConfigCache.reload_clients()

    def set_main_account(self, account_hash: str, account_number: str):
        """Установить главный аккаунт"""
        self.main_account = {
            'account_hash': account_hash,
            'account_number': account_number
        }
        self.save_clients()

    def add_client(
            self,
            account_hash: str,
            account_number: str,
            name: str,
            settings: Dict
    ) -> ClientConfig:
        """Добавить нового клиента"""
        # Генерировать ID
        client_id = f"slave_{len(self.clients) + 1}"

        client_data = {
            'id': client_id,
            'account_hash': account_hash,
            'account_number': account_number,
            'name': name,
            'enabled': True,
            'settings': settings
        }

        client = ClientConfig(client_data)
        self.clients.append(client)
        self.save_clients()

        return client

    def remove_client(self, client_id: str) -> bool:
        """Удалить клиента"""
        self.clients = [c for c in self.clients if c.id != client_id]
        self.save_clients()
        return True

    def update_client(self, client_id: str, updates: Dict) -> bool:
        """Обновить настройки клиента"""
        for client in self.clients:
            if client.id == client_id:
                for key, value in updates.items():
                    if key == 'settings':
                        client.settings.update(value)
                    else:
                        setattr(client, key, value)
                self.save_clients()
                return True
        return False

    def get_client(self, client_id: str) -> Optional[ClientConfig]:
        """Получить клиента по ID"""
        for client in self.clients:
            if client.id == client_id:
                return client
        return None

    def get_enabled_clients(self) -> List[ClientConfig]:
        """Получить только активных клиентов"""
        return [c for c in self.clients if c.enabled]

    def toggle_client(self, client_id: str) -> bool:
        """Включить/выключить клиента"""
        for client in self.clients:
            if client.id == client_id:
                client.enabled = not client.enabled
                self.save_clients()
                return client.enabled
        return False