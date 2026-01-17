
# paths.py
# app.core.paths

from pathlib import Path

# Корневая директория проекта (SyncSchwab/)
ROOT_DIR = Path(__file__).parent.parent.parent

# Основные директории
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
TESTS_DIR = ROOT_DIR / "tests"
TMP_DIR = ROOT_DIR / "tmp"

# Поддиректории в data/
DATA_CLIENTS_DIR = DATA_DIR / "clients"

# Токены (создаем отдельную папку для токенов в корне)
TOKEN_PATH = ROOT_DIR / "tokens"

# Создать необходимые директории при импорте
CONFIG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
DATA_CLIENTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
TOKEN_PATH.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# Основные файлы конфигурации
CLIENTS_CONFIG_FILE = CONFIG_DIR / "clients.json"
GENERAL_SETTINGS_FILE = CONFIG_DIR / "general_settings.json"

# Файлы данных
SYNC_HISTORY_FILE = DATA_DIR / "sync_history.json"
ORDERS_LOG_FILE = DATA_DIR / "orders_log.json"

# Файл .env (в корне проекта)
ENV_FILE = ROOT_DIR / ".env"

# Файлы логов
MAIN_LOG_FILE = LOGS_DIR / "schwab_client.log"


# Вспомогательные функции
def get_client_history_file(client_id: str) -> Path:
    """
    Получить путь к файлу истории клиента

    Args:
        client_id: ID клиента (например: slave_1)

    Returns:
        Path к файлу истории
    """
    return DATA_CLIENTS_DIR / f"{client_id}_history.json"


def get_client_tokens_file(client_id: str) -> Path:
    """
    Получить путь к файлу токенов клиента

    Args:
        client_id: ID клиента (например: slave_1, main)

    Returns:
        Path к файлу токенов
    """
    return TOKEN_PATH / f"{client_id}_tokens.json"


def get_client_history_dry_file(client_id: str) -> Path:
    """
    Получить путь к файлу DRY истории клиента (для SIMULATION режима)

    Args:
        client_id: ID клиента (например: slave_1)

    Returns:
        Path к файлу DRY истории
    """
    return DATA_CLIENTS_DIR / f"{client_id}_history_dry.json"


# Файлы кэша
ACCOUNT_CACHE_FILE = DATA_DIR / "account_cache.json"
ACCOUNT_CACHE_DRY_FILE = DATA_DIR / "account_cache_dry.json"


# Проверка существования критических файлов при импорте
if not ENV_FILE.exists():
    print(f"⚠️  Warning: .env file not found at {ENV_FILE}")
    print(f"   Please create it with your Schwab API credentials")

# Вывод информации о путях (только для отладки)
if __name__ == "__main__":
    print("=" * 60)
    print("📁 Project Paths Configuration")
    print("=" * 60)
    print(f"Root Directory:       {ROOT_DIR}")
    print(f"Config Directory:     {CONFIG_DIR}")
    print(f"Data Directory:       {DATA_DIR}")
    print(f"Logs Directory:       {LOGS_DIR}")
    print(f"Tokens Directory:     {TOKEN_PATH}")
    print(f"Temp Directory:       {TMP_DIR}")
    print("=" * 60)
    print(f"Clients Config:       {CLIENTS_CONFIG_FILE}")
    print(f"General Settings:     {GENERAL_SETTINGS_FILE}")
    print(f"Sync History:         {SYNC_HISTORY_FILE}")
    print(f"Orders Log:           {ORDERS_LOG_FILE}")
    print(f"Environment File:     {ENV_FILE}")
    print("=" * 60)
    print(f"✅ All directories exist: {all([d.exists() for d in [CONFIG_DIR, DATA_DIR, LOGS_DIR, TOKEN_PATH]])}")

"""
# В любом файле проекта
from app.core.paths import (
    CONFIG_DIR,
    DATA_DIR,
    TOKEN_PATH,
    CLIENTS_CONFIG_FILE,
    get_client_history_file,
    get_client_tokens_file
)

# Примеры:
history_file = get_client_history_file('slave_1')
# → SyncSchwab/data/clients/slave_1_history.json

tokens_file = get_client_tokens_file('main')
# → SyncSchwab/tokens/main_tokens.json
"""