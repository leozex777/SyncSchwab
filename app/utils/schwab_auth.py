
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

    Args:
        force_new: Если True - принудительная переавторизация

    Returns:
        True если токен успешно получен
    """
    logger.info("Starting Main Account authorization...")

    try:
        import schwabdev

        app_key = os.getenv('MAIN_KEY_ID')
        app_secret = os.getenv('MAIN_CLIENT_SECRET')
        callback_url = os.getenv('MAIN_REDIRECT_URI', 'https://127.0.0.1:8182')

        if not all([app_key, app_secret]):
            logger.error("Main account credentials not found in .env")
            return False

        token_file = TOKEN_PATH / "main_tokens.json"

        # Принудительная переавторизация - сделать токен просроченным
        if force_new:
            _expire_token_file(token_file)

        logger.info(f"Token file: {token_file}")
        logger.info(f"Callback URL: {callback_url}")

        # schwabdev увидит просроченный токен и откроет браузер
        _ = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file),
            capture_callback=True
        )

        # Проверить что токен обновлен
        if token_file.exists():
            logger.info("Main Account authorization successful")

            # Сохранить account_hash в client_manager
            try:
                import streamlit as st
                from app.core.config import get_hash_account

                account_number = os.getenv('MAIN_ACCOUNT_NUMBER')

                if account_number and 'client_manager' in st.session_state:
                    # Создать временный client для получения hash
                    client = schwabdev.Client(
                        app_key=app_key,
                        app_secret=app_secret,
                        callback_url=callback_url,
                        tokens_file=str(token_file),
                        capture_callback=True
                    )

                    account_hash = get_hash_account(client, account_number)

                    if account_hash:
                        st.session_state.client_manager.set_main_account(
                            account_hash=account_hash,
                            account_number=account_number
                        )
                        logger.info(f"Main account hash saved after auth: {account_hash[:8]}...")
            except Exception as e:
                logger.warning(f"Could not save account_hash after auth: {e}")
            return True

        else:
            logger.error("Token file not created after authorization")
            return False

    except Exception as e:
        logger.error(f"Main Account authorization failed: {e}")
        return False


def authorize_client(client_id: str, force_new: bool = True) -> bool:
    """
    Авторизация клиента через schwabdev.

    Args:
        client_id: ID клиента (например, 'slave_1')
        force_new: Если True - принудительная переавторизация

    Returns:
        True если токен успешно получен
    """
    logger.info(f"Starting authorization for client: {client_id}")

    try:
        import schwabdev

        env_prefix = client_id.upper()
        app_key = os.getenv(f'{env_prefix}_KEY_ID')
        app_secret = os.getenv(f'{env_prefix}_CLIENT_SECRET')
        callback_url = os.getenv(f'{env_prefix}_REDIRECT_URI', 'https://127.0.0.1:8182')

        if not all([app_key, app_secret]):
            logger.error(f"Client {client_id} credentials not found in .env")
            return False

        token_file = TOKEN_PATH / f"{client_id}_tokens.json"

        # Принудительная переавторизация - сделать токен просроченным
        if force_new:
            _expire_token_file(token_file)

        logger.info(f"Token file: {token_file}")
        logger.info(f"Callback URL: {callback_url}")

        # schwabdev увидит просроченный токен и откроет браузер
        _ = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file),
            capture_callback=True
        )

        if token_file.exists():
            logger.info(f"Client {client_id} authorization successful")
            return True
        else:
            logger.error(f"Client {client_id} token file not created")
            return False

    except Exception as e:
        logger.error(f"Client {client_id} authorization failed: {e}")
        return False