
# env_manager.py
# app.gui.utils.env_manager

import os
from pathlib import Path
from dotenv import load_dotenv, set_key


def save_main_account_to_env(account_data: dict):
    """Сохранить данные главного аккаунта в .env"""
    env_file = Path('.env')

    if not env_file.exists():
        env_file.touch()

    set_key(str(env_file), "MAIN_ACCOUNT_NUMBER", account_data['account_number'])
    set_key(str(env_file), "MAIN_KEY_ID", account_data['key_id'])
    set_key(str(env_file), "MAIN_CLIENT_SECRET", account_data['client_secret'])
    set_key(str(env_file), "MAIN_REDIRECT_URI", account_data['redirect_uri'])


def load_main_account_from_env() -> dict:
    """Загрузить данные главного аккаунта из .env"""
    load_dotenv()

    return {
        'account_number': os.getenv("MAIN_ACCOUNT_NUMBER"),
        'key_id': os.getenv("MAIN_KEY_ID"),
        'client_secret': os.getenv("MAIN_CLIENT_SECRET"),
        'redirect_uri': os.getenv("MAIN_REDIRECT_URI")
    }


def save_client_to_env(client_id: str, client_data: dict):
    """Сохранить данные клиента в .env файл"""
    env_file = Path('.env')

    if not env_file.exists():
        env_file.touch()

    client_num = client_id.split('_')[1]
    prefix = f"SLAVE_{client_num}_"

    set_key(str(env_file), f"{prefix}NAME", client_data['name'])
    set_key(str(env_file), f"{prefix}ACCOUNT_NUMBER", client_data['account_number'])
    set_key(str(env_file), f"{prefix}KEY_ID", client_data['key_id'])
    set_key(str(env_file), f"{prefix}CLIENT_SECRET", client_data['client_secret'])
    set_key(str(env_file), f"{prefix}REDIRECT_URI", client_data['redirect_uri'])


def load_client_from_env(client_id: str) -> dict:
    """Загрузить данные клиента из .env"""
    load_dotenv()

    client_num = client_id.split('_')[1]
    prefix = f"SLAVE_{client_num}_"

    return {
        'name': os.getenv(f"{prefix}NAME"),
        'account_number': os.getenv(f"{prefix}ACCOUNT_NUMBER"),
        'key_id': os.getenv(f"{prefix}KEY_ID"),
        'client_secret': os.getenv(f"{prefix}CLIENT_SECRET"),
        'redirect_uri': os.getenv(f"{prefix}REDIRECT_URI")
    }


def delete_client_from_env(client_id: str):
    """Удалить данные клиента из .env"""
    env_file = Path('.env')
    if not env_file.exists():
        return

    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    client_num = client_id.split('_')[1]
    prefix = f"SLAVE_{client_num}_"

    filtered_lines = [line for line in lines if not line.startswith(prefix)]

    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(filtered_lines)