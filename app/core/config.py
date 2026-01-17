
# config.ry
# app.core.config

import os
from typing import Optional, Dict, List
from dotenv import load_dotenv
import schwabdev
from app.core.logger import logger
from app.core.paths import TOKEN_PATH

# Загрузить .env
load_dotenv()

# ========== ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ==========
# НЕ создавать client при импорте!
_main_client: Optional[schwabdev.Client] = None
_slave_clients: Dict[str, schwabdev.Client] = {}  # Кэш slave клиентов


def reset_client_cache():
    """
    Сбросить кэш клиентов.
    Вызывается при Start для "чистого старта" с новыми клиентами.
    """
    global _main_client, _slave_clients
    _main_client = None
    _slave_clients = {}
    logger.debug("Client cache reset")


def get_main_client() -> Optional[schwabdev.Client]:
    """
    Получить Main Account client (ленивая инициализация)

    Returns:
        Client или None если токена нет
    """
    global _main_client

    # Если client уже создан - вернуть его
    if _main_client is not None:
        return _main_client

    # Проверить есть ли токен
    token_file = TOKEN_PATH / "main_tokens.json"
    if not token_file.exists():
        logger.warning("Main account token not found")
        return None

    # Создать client
    try:
        _main_client = build_main_client()
        return _main_client
    except Exception as e:
        logger.error(f"Failed to create main client: {e}")
        return None


def build_main_client() -> schwabdev.Client:
    """
    Создать Schwab client для Main Account

    Returns:
        schwabdev.Client instance
    """
    main_key_id = os.getenv('MAIN_KEY_ID')
    main_client_secret = os.getenv('MAIN_CLIENT_SECRET')
    main_redirect_uri = os.getenv('MAIN_REDIRECT_URI', 'https://127.0.0.1:8182')

    if not all([main_key_id, main_client_secret]):
        raise ValueError("Main account credentials not found in .env")

    token_file = TOKEN_PATH / "main_tokens.json"

    schwab_client = schwabdev.Client(
        app_key=main_key_id,
        app_secret=main_client_secret,
        callback_url=main_redirect_uri,
        tokens_file=str(token_file),
        capture_callback=True
    )

    logger.info("Main account client created")
    return schwab_client


def build_client_for_slave(
        client_id: str,
        app_key: str,
        app_secret: str,
        callback_url: str
) -> schwabdev.Client:
    """
    Создать Schwab client для Slave Account

    Args:
        client_id: ID клиента (например: slave_1)
        app_key: App Key
        app_secret: App Secret
        callback_url: Redirect URI

    Returns:
        schwabdev.Client instance
    """
    token_file = TOKEN_PATH / f"{client_id}_tokens.json"

    schwab_client = schwabdev.Client(
        app_key=app_key,
        app_secret=app_secret,
        callback_url=callback_url,
        tokens_file=str(token_file),
        capture_callback=True
    )

    logger.info(f"Slave client created for {client_id}")
    return schwab_client


def get_slave_client(
        client_id: str,
        app_key: str,
        app_secret: str,
        callback_url: str
) -> Optional[schwabdev.Client]:
    """
    Получить Slave client с кэшированием.
    
    Args:
        client_id: ID клиента (например: slave_1)
        app_key: App Key
        app_secret: App Secret  
        callback_url: Redirect URI
        
    Returns:
        schwabdev.Client или None если не удалось создать
    """
    global _slave_clients
    
    # Если client уже в кэше - вернуть его
    if client_id in _slave_clients:
        return _slave_clients[client_id]
    
    # Проверить существование токена ПЕРЕД созданием Client
    token_file = TOKEN_PATH / f"{client_id}_tokens.json"
    if not token_file.exists():
        logger.warning(f"Slave account {client_id} token not found")
        return None
    
    # Создать и закэшировать
    try:
        client = build_client_for_slave(client_id, app_key, app_secret, callback_url)
        _slave_clients[client_id] = client
        logger.debug(f"Slave client {client_id} cached")
        return client
    except Exception as e:
        logger.error(f"Failed to create slave client {client_id}: {e}")
        return None


def clear_client_cache():
    """
    Очистить кэш всех клиентов.
    Используется при ошибках авторизации или перезапуске.
    """
    global _main_client, _slave_clients
    _main_client = None
    _slave_clients = {}
    logger.info("Client cache cleared")


def get_linked_accounts(schwab_client: schwabdev.Client) -> List[Dict]:
    """
    Получить список привязанных аккаунтов

    Args:
        schwab_client: Schwab client instance

    Returns:
        List of account dictionaries
    """
    try:
        response = schwab_client.account_linked().json()
        return response
    except Exception as e:
        logger.error(f"Failed to get linked accounts: {e}")
        return []


def get_hash_account(schwab_client: schwabdev.Client, account_number: str) -> Optional[str]:
    """
    Получить hash аккаунта по номеру

    Args:
        schwab_client: Schwab client instance
        account_number: Номер аккаунта

    Returns:
        Hash аккаунта или None
    """
    try:
        accounts = get_linked_accounts(schwab_client)

        for account in accounts:
            if account.get('accountNumber') == account_number:
                return account.get('hashValue')

        logger.warning(f"Account {account_number} not found in linked accounts")
        return None

    except Exception as e:
        logger.error(f"Failed to get account hash: {e}")
        return None


def get_account_number_by_hash(schwab_client: schwabdev.Client, hash_value: str) -> Optional[str]:
    """
    Получить номер аккаунта по hash

    Args:
        schwab_client: Schwab client instance
        hash_value: Hash аккаунта

    Returns:
        Номер аккаунта или None
    """
    try:
        accounts = get_linked_accounts(schwab_client)

        for account in accounts:
            if account.get('hashValue') == hash_value:
                return account.get('accountNumber')

        logger.warning(f"Hash {hash_value} not found in linked accounts")
        return None

    except Exception as e:
        logger.error(f"Failed to get account number: {e}")
        return None


def verify_main_account() -> bool:
    """
    Проверить конфигурацию Main Account

    Returns:
        True если всё настроено правильно
    """
    token_file = TOKEN_PATH / "main_tokens.json"

    if not token_file.exists():
        logger.error("Main account token not found")
        return False

    main_key_id = os.getenv('MAIN_KEY_ID')
    main_client_secret = os.getenv('MAIN_CLIENT_SECRET')

    if not all([main_key_id, main_client_secret]):
        logger.error("Main account credentials not configured")
        return False

    try:
        schwab_client = get_main_client()
        if schwab_client is None:
            return False

        # Проверить что client работает
        accounts = get_linked_accounts(schwab_client)
        if not accounts:
            logger.error("No linked accounts found")
            return False

        logger.info("Main account verified successfully")
        return True

    except Exception as e:
        logger.error(f"Main account verification failed: {e}")
        return False


def verify_slave_account(
        client_id: str,
        account_number: str,
        app_key: str,
        app_secret: str,
        callback_url: str
) -> bool:
    """
    Проверить конфигурацию Slave Account

    Args:
        client_id: ID клиента
        account_number: Номер аккаунта
        app_key: App Key
        app_secret: App Secret
        callback_url: Redirect URI

    Returns:
        True если всё настроено правильно
    """
    token_file = TOKEN_PATH / f"{client_id}_tokens.json"

    if not token_file.exists():
        logger.error(f"Slave account {client_id} token not found")
        return False

    try:
        schwab_client = build_client_for_slave(
            client_id,
            app_key,
            app_secret,
            callback_url
        )

        # Проверить что аккаунт доступен
        account_hash = get_hash_account(schwab_client, account_number)

        if not account_hash:
            logger.error(f"Account {account_number} not found for {client_id}")
            return False

        logger.info(f"Slave account {client_id} verified successfully")
        return True

    except Exception as e:
        logger.error(f"Slave account {client_id} verification failed: {e}")
        return False