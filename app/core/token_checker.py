
# token_checker.py
# app.core.token_checker

from typing import Dict
from datetime import datetime, timedelta
from app.core.paths import TOKEN_PATH
from app.core.json_utils import load_json
from app.core.logger import logger
from app.models.clients.client_manager import ClientManager
import os
from dotenv import load_dotenv

load_dotenv()


def check_token_validity(token_file_path) -> Dict:
    """
    Проверить валидность токена по refresh_token
    """
    result = {
        'has_token': False,
        'has_refresh_token': False,
        'is_valid': False,
        'needs_auth': True,
        'message': ''
    }

    logger.debug(f"Checking token: {token_file_path}")

    try:
        tokens = load_json(str(token_file_path))

        if not tokens:
            result['message'] = "❌ Token file empty"
            logger.debug("Token file empty")
            return result

        result['has_token'] = True

        # schwabdev хранит токены в token_dictionary
        token_dict = tokens.get('token_dictionary', {})

        # Проверить наличие refresh_token
        refresh_token = token_dict.get('refresh_token')
        if not refresh_token:
            result['message'] = "❌ No refresh_token"
            logger.warning("No refresh_token in token file")
            return result

        result['has_refresh_token'] = True

        # Проверить срок действия refresh_token (7 дней)
        refresh_token_issued = tokens.get('refresh_token_issued')

        if refresh_token_issued:
            try:
                issued_str = str(refresh_token_issued)
                
                # Парсить timestamp и конвертировать в UTC
                # Формат: 2026-01-18T18:53:36.665041+00:00
                from datetime import timezone
                
                # Убрать timezone часть для парсинга, потом добавить UTC
                if '+' in issued_str:
                    # Есть timezone offset
                    base_str = issued_str.split('+')[0]
                    tz_str = '+' + issued_str.split('+')[1]
                    
                    # Парсим base datetime
                    issued_dt_naive = datetime.fromisoformat(base_str)
                    
                    # Парсим offset (например +00:00 или +02:00)
                    tz_parts = tz_str.replace('+', '').replace('-', '').split(':')
                    tz_hours = int(tz_parts[0])
                    tz_minutes = int(tz_parts[1]) if len(tz_parts) > 1 else 0
                    if tz_str.startswith('-'):
                        tz_hours = -tz_hours
                    
                    # Конвертируем в UTC
                    issued_dt_utc = issued_dt_naive - timedelta(hours=tz_hours, minutes=tz_minutes)
                    issued_dt = issued_dt_utc.replace(tzinfo=timezone.utc)
                    
                elif 'Z' in issued_str:
                    # Z = UTC
                    issued_dt = datetime.fromisoformat(issued_str.replace('Z', '')).replace(tzinfo=timezone.utc)
                else:
                    # Без timezone - считаем UTC
                    issued_dt = datetime.fromisoformat(issued_str).replace(tzinfo=timezone.utc)
                
                expires_dt = issued_dt + timedelta(days=7)
                
                # Текущее время в UTC
                now = datetime.now(timezone.utc)

                if now > expires_dt:
                    result['message'] = "❌ Refresh token expired (>7 days)"
                    logger.warning(f"Refresh token expired: issued {issued_dt}, expired {expires_dt}")
                    return result

                remaining = expires_dt - now
                days_left = remaining.days
                hours_left = remaining.seconds // 3600

                result['is_valid'] = True
                result['needs_auth'] = False
                result['message'] = f"✅ Valid ({days_left}d {hours_left}h left)"

                logger.debug(f"Token valid: {days_left}d {hours_left}h remaining")
                return result

            except (ValueError, TypeError) as e:
                logger.debug(f"Could not parse token date: {e}")
                result['is_valid'] = True
                result['needs_auth'] = False
                result['message'] = "✅ Valid (date unknown)"
                return result

        # Если нет даты - проверяем просто наличие refresh_token
        if refresh_token:
            result['is_valid'] = True
            result['needs_auth'] = False
            result['message'] = "✅ Valid"

        return result

    except FileNotFoundError:
        result['message'] = "❌ Token file not found"
        logger.debug(f"Token file not found: {token_file_path}")
        return result
    except (KeyError, TypeError, ValueError) as e:
        result['message'] = f"❌ Token error: {e}"
        logger.error(f"Token check error: {e}")
        return result


def check_main_account_token() -> Dict:
    """Проверить статус токена Main Account"""

    logger.debug("Checking main account token...")

    result = {
        'has_token': False,
        'is_valid': False,
        'needs_auth': True,
        'message': '',
        'credentials_ok': False
    }

    # Проверить credentials в .env
    main_key_id = os.getenv('MAIN_KEY_ID')
    main_client_secret = os.getenv('MAIN_CLIENT_SECRET')
    main_account_number = os.getenv('MAIN_ACCOUNT_NUMBER')

    if not all([main_key_id, main_client_secret, main_account_number]):
        result['message'] = "❌ Credentials not found in .env"
        logger.warning("Main account credentials not found in .env")
        return result

    result['credentials_ok'] = True

    # Проверить токен файл
    token_file = TOKEN_PATH / "main_tokens.json"

    if not token_file.exists():
        result['message'] = "❌ Token not found"
        logger.debug("Main token file not found")
        return result

    # Проверить валидность refresh_token
    token_status = check_token_validity(token_file)

    result['has_token'] = token_status['has_token']
    result['is_valid'] = token_status['is_valid']
    result['needs_auth'] = token_status['needs_auth']
    result['message'] = token_status['message']

    logger.debug(f"Main account token status: valid={result['is_valid']}")
    return result


def check_client_token(client_id: str, client_name: str) -> Dict:
    """Проверить статус токена клиента"""

    logger.debug(f"Checking client token: {client_id}")

    result = {
        'client_id': client_id,
        'client_name': client_name,
        'has_token': False,
        'is_valid': False,
        'needs_auth': True,
        'message': '',
        'credentials_ok': False
    }

    # Проверить credentials в .env
    key_id = os.getenv(f'{client_id.upper()}_KEY_ID')
    client_secret = os.getenv(f'{client_id.upper()}_CLIENT_SECRET')
    account_number = os.getenv(f'{client_id.upper()}_ACCOUNT_NUMBER')

    if not all([key_id, client_secret, account_number]):
        result['message'] = "❌ Credentials not found in .env"
        logger.warning(f"Client {client_id} credentials not found in .env")
        return result

    result['credentials_ok'] = True

    # Проверить токен файл
    token_file = TOKEN_PATH / f"{client_id}_tokens.json"

    if not token_file.exists():
        result['message'] = "❌ Token not found"
        logger.debug(f"Client {client_id} token file not found")
        return result

    # Проверить валидность refresh_token
    token_status = check_token_validity(token_file)

    result['has_token'] = token_status['has_token']
    result['is_valid'] = token_status['is_valid']
    result['needs_auth'] = token_status['needs_auth']
    result['message'] = token_status['message']

    logger.debug(f"Client {client_id} token status: valid={result['is_valid']}")
    return result


def check_all_tokens(client_manager: ClientManager) -> Dict:
    """Проверить все токены (Main + Clients)"""

    logger.debug("Checking all tokens...")

    # Проверить Main Account
    main_status = check_main_account_token()

    # Проверить всех клиентов
    clients_status = []

    for client_config in client_manager.clients:
        client_status = check_client_token(client_config.id, client_config.name)
        # Добавить is_enabled из конфига клиента
        client_status['is_enabled'] = client_config.enabled
        clients_status.append(client_status)

    # Статистика
    total_clients = len(clients_status)
    authorized_clients = sum(1 for c in clients_status if c['is_valid'])
    needs_auth_clients = sum(1 for c in clients_status if c['needs_auth'])

    logger.debug(f"Token check: main={main_status['is_valid']}, "
                 f"clients={authorized_clients}/{total_clients} authorized")

    return {
        'main': main_status,
        'clients': clients_status,
        'total_clients': total_clients,
        'authorized_clients': authorized_clients,
        'needs_auth_clients': needs_auth_clients
    }


def refresh_token_if_needed(token_file_path, app_key: str, app_secret: str, callback_url: str) -> bool:
    """Обновить access_token используя refresh_token если нужно"""

    logger.debug(f"Attempting to refresh token: {token_file_path}")

    try:
        import schwabdev

        _ = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_file=str(token_file_path)
        )

        logger.debug("Token refreshed successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to refresh token: {e}")
        return False