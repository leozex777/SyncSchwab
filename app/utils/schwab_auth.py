
# schwab_auth.py
# app.utils.schwab_auth

import os
import json
from datetime import datetime, timedelta, timezone

from app.core.paths import TOKEN_PATH
from app.core.logger import logger
from dotenv import load_dotenv

load_dotenv()


def _expire_token_file(token_file) -> bool:
    """
    Сделать токен просроченным, изменив дату refresh_token_issued.
    schwabdev увидит что токен старше 7 дней и запустит OAuth.

    Args:
        token_file: Путь к файлу токена

    Returns:
        True если успешно
    """
    if not token_file.exists():
        return False

    try:
        with open(token_file, 'r') as f:
            tokens = json.load(f)

        # Установить дату выдачи refresh_token на 8 дней назад
        old_date = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        tokens['refresh_token_issued'] = old_date

        with open(token_file, 'w') as f:
            json.dump(tokens, f, indent=4)

        logger.info(f"Token expired: refresh_token_issued set to {old_date}")
        return True

    except Exception as e:
        logger.error(f"Failed to expire token: {e}")
        return False


def authorize_main_account(force_new: bool = True) -> bool:
    """
    Авторизация Main Account через schwabdev.
    Открывает браузер, ждет callback, сохраняет токен.
    
    После авторизации проверяет что аккаунт соответствует MAIN_ACCOUNT_NUMBER.
    Если нет — удаляет токен и возвращает ошибку.

    Args:
        force_new: Если True - принудительная переавторизация

    Returns:
        True если токен успешно получен и аккаунт правильный
    """
    logger.info("Starting Main Account authorization...")

    try:
        import schwabdev

        app_key = os.getenv('MAIN_KEY_ID')
        app_secret = os.getenv('MAIN_CLIENT_SECRET')
        callback_url = os.getenv('MAIN_REDIRECT_URI', 'https://127.0.0.1:8182')
        expected_account_number = os.getenv('MAIN_ACCOUNT_NUMBER')

        if not all([app_key, app_secret]):
            logger.error("Main account credentials not found in .env")
            return False

        token_file = TOKEN_PATH / "main_tokens.json"

        # Принудительная переавторизация - сделать токен просроченным
        if force_new:
            _expire_token_file(token_file)

        logger.info(f"Token file: {token_file}")
        logger.info(f"Callback URL: {callback_url}")

        # schwabdev откроет браузер для OAuth
        client = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file),
            capture_callback=True
        )

        # Проверить что токен создан
        if not token_file.exists():
            logger.error("Token file not created after authorization")
            return False

        # ═══════════════════════════════════════════════════════════════
        # ПРОВЕРКА: Убедиться что авторизован ПРАВИЛЬНЫЙ аккаунт
        # ═══════════════════════════════════════════════════════════════
        if expected_account_number:
            try:
                # Получить список аккаунтов из API
                response = client.account_linked().json()
                
                # Найти account_number в списке
                authorized_accounts = [acc.get('accountNumber') for acc in response]
                
                if expected_account_number not in authorized_accounts:
                    # ОШИБКА: Авторизован неправильный аккаунт!
                    logger.error(f"⚠️ WRONG ACCOUNT AUTHORIZED!")
                    logger.error(f"Expected: {expected_account_number}")
                    logger.error(f"Got: {authorized_accounts}")
                    
                    # Удалить неправильный токен
                    token_file.unlink()
                    logger.info("Invalid token deleted")
                    
                    return False
                
                # Получить account_hash для правильного аккаунта
                account_hash = None
                for acc in response:
                    if acc.get('accountNumber') == expected_account_number:
                        account_hash = acc.get('hashValue')
                        break
                
                # Сохранить account_hash в client_manager
                if account_hash:
                    try:
                        import streamlit as st
                        if 'client_manager' in st.session_state:
                            st.session_state.client_manager.set_main_account(
                                account_hash=account_hash,
                                account_number=expected_account_number
                            )
                            logger.info(f"Main account hash saved: {account_hash[:8]}...")
                    except Exception as e:
                        logger.warning(f"Could not save account_hash: {e}")
                        
            except Exception as e:
                logger.warning(f"Could not verify account: {e}")
                # Продолжаем — токен создан, но не смогли проверить

        logger.info("Main Account authorization successful")
        
        # Сбросить кэш клиентов чтобы использовать новые токены
        from app.core.config import clear_client_cache
        clear_client_cache()
        logger.debug("Client cache reset after authorization")
        
        return True

    except Exception as e:
        logger.error(f"Main Account authorization failed: {e}")
        return False


def authorize_client(client_id: str, force_new: bool = True) -> bool:
    """
    Авторизация клиента через schwabdev.
    
    После авторизации проверяет что аккаунт соответствует ожидаемому.
    Если нет — удаляет токен и возвращает ошибку.

    Args:
        client_id: ID клиента (например, 'slave_1')
        force_new: Если True - принудительная переавторизация

    Returns:
        True если токен успешно получен и аккаунт правильный
    """
    logger.info(f"Starting authorization for client: {client_id}")

    try:
        import schwabdev

        env_prefix = client_id.upper()
        app_key = os.getenv(f'{env_prefix}_KEY_ID')
        app_secret = os.getenv(f'{env_prefix}_CLIENT_SECRET')
        callback_url = os.getenv(f'{env_prefix}_REDIRECT_URI', 'https://127.0.0.1:8182')
        expected_account_number = os.getenv(f'{env_prefix}_ACCOUNT_NUMBER')

        if not all([app_key, app_secret]):
            logger.error(f"Client {client_id} credentials not found in .env")
            return False

        token_file = TOKEN_PATH / f"{client_id}_tokens.json"

        # Принудительная переавторизация - сделать токен просроченным
        if force_new:
            _expire_token_file(token_file)

        logger.info(f"Token file: {token_file}")
        logger.info(f"Callback URL: {callback_url}")

        # schwabdev откроет браузер для OAuth
        client = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file),
            capture_callback=True
        )

        # Проверить что токен создан
        if not token_file.exists():
            logger.error(f"Client {client_id} token file not created")
            return False

        # ═══════════════════════════════════════════════════════════════
        # ПРОВЕРКА: Убедиться что авторизован ПРАВИЛЬНЫЙ аккаунт
        # ═══════════════════════════════════════════════════════════════
        if expected_account_number:
            try:
                # Получить список аккаунтов из API
                response = client.account_linked().json()
                
                # Найти account_number в списке
                authorized_accounts = [acc.get('accountNumber') for acc in response]
                
                if expected_account_number not in authorized_accounts:
                    # ОШИБКА: Авторизован неправильный аккаунт!
                    logger.error(f"⚠️ WRONG ACCOUNT AUTHORIZED for {client_id}!")
                    logger.error(f"Expected: {expected_account_number}")
                    logger.error(f"Got: {authorized_accounts}")
                    
                    # Удалить неправильный токен
                    token_file.unlink()
                    logger.info(f"Invalid token for {client_id} deleted")
                    
                    return False
                    
            except Exception as e:
                logger.warning(f"Could not verify account for {client_id}: {e}")
                # Продолжаем — токен создан, но не смогли проверить

        logger.info(f"Client {client_id} authorization successful")
        
        # Сбросить кэш клиентов чтобы использовать новые токены
        from app.core.config import clear_client_cache
        clear_client_cache()
        logger.debug("Client cache reset after authorization")
        
        return True

    except Exception as e:
        logger.error(f"Client {client_id} authorization failed: {e}")
        return False
