
# test_all_accounts.py
# scripts.test_all_accounts
#
# Выводит данные всех аккаунтов (Main + Clients)
# Запуск: python scripts/test_all_accounts.py

import sys
import os
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from app.core.config import get_main_client, build_client_for_slave
from app.core.json_utils import load_json
from app.gui.utils.env_manager import load_client_from_env


def get_account_data(client, account_number=None):
    """Получить данные аккаунта"""
    accounts = client.account_linked().json()
    
    for acc in accounts:
        acc_num = acc.get('accountNumber')
        
        # Если указан номер — искать конкретный
        if account_number and acc_num != account_number:
            continue
            
        hash_value = acc.get('hashValue')
        details = client.account_details(hash_value, fields='positions').json()
        
        sa = details.get('securitiesAccount', {})
        balances = sa.get('currentBalances', {})
        positions = sa.get('positions', [])
        
        # Рассчитать positions value
        positions_value = sum(
            p.get('marketValue', 0) 
            for p in positions
        )
        
        return {
            'account_number': acc_num,
            'total_value': balances.get('liquidationValue', 0),
            'positions_value': positions_value,
            'cash_balance': balances.get('cashBalance', 0),
            'buying_power': balances.get('buyingPower', 0),
            'day_trading_buying_power': balances.get('dayTradingBuyingPower', 0),
            'available_funds': balances.get('availableFunds', 0),
            'positions_count': len(positions)
        }
    
    return None


def print_account(name, data):
    """Красиво вывести данные аккаунта"""
    if not data:
        print(f"\n{name}: ❌ Could not load data")
        return
        
    print(f"\n{'='*50}")
    print(f"{name}: {data['account_number']}")
    print(f"{'='*50}")
    print(f"  Total Value:             ${data['total_value']:>12,.2f}")
    print(f"  Positions Value:         ${data['positions_value']:>12,.2f}")
    print(f"  cashBalance:             ${data['cash_balance']:>12,.2f}")
    print(f"  buyingPower:             ${data['buying_power']:>12,.2f}")
    print(f"  dayTradingBuyingPower:   ${data['day_trading_buying_power']:>12,.2f}")
    print(f"  availableFunds:          ${data['available_funds']:>12,.2f}")
    print(f"  Open Positions:          {data['positions_count']:>12}")
    
    # Показать есть ли маржа
    if data['buying_power'] > data['cash_balance'] * 1.1:
        print(f"  {'─'*40}")
        print(f"  ✅ Margin ENABLED by Schwab")
    else:
        print(f"  {'─'*40}")
        print(f"  ❌ Margin NOT available")


def main():
    print("\n" + "="*50)
    print("       ALL ACCOUNTS OVERVIEW")
    print("="*50)
    
    # ═══════════════════════════════════════════════════
    # MAIN ACCOUNT
    # ═══════════════════════════════════════════════════
    
    main_client = get_main_client()
    if main_client:
        main_account_number = os.getenv('MAIN_ACCOUNT_NUMBER')
        data = get_account_data(main_client, main_account_number)
        print_account("Main Account", data)
    else:
        print("\n❌ Main Account: Not configured")
    
    # ═══════════════════════════════════════════════════
    # SLAVE ACCOUNTS
    # ═══════════════════════════════════════════════════
    
    # Попробовать разные пути к clients.json
    possible_paths = [
        "config/clients.json",
        "config\\clients.json",
        "../config/clients.json",
        "clients.json",
        "data/clients.json"
    ]
    
    clients_data = {}
    for path in possible_paths:
        clients_data = load_json(path, default={})
        if clients_data:
            print(f"\n📂 Found clients.json at: {path}")
            break
    
    if not clients_data:
        print("\n❌ clients.json not found in any expected location")
        print("   Tried:", possible_paths)
        return
        
    slave_accounts = clients_data.get('slave_accounts', [])
    
    for slave in slave_accounts:
        client_id = slave.get('id')
        client_name = slave.get('name', client_id)
        account_number = slave.get('account_number')
        enabled = slave.get('enabled', False)
        
        if not enabled:
            print(f"\n{'='*50}")
            print(f"{client_name} Account: {account_number}")
            print(f"{'='*50}")
            print(f"  ⏸️ DISABLED - skipping")
            continue
        
        try:
            env_data = load_client_from_env(client_id)
            
            if not env_data.get('key_id'):
                print(f"\n{client_name} Account: ❌ Credentials not configured")
                continue
            
            slave_client = build_client_for_slave(
                client_id,
                env_data['key_id'],
                env_data['client_secret'],
                env_data.get('redirect_uri', 'https://127.0.0.1:8182')
            )
            
            data = get_account_data(slave_client, account_number)
            print_account(f"{client_name} Account", data)
            
        except Exception as e:
            print(f"\n{client_name} Account: ❌ Error: {e}")
    
    print("\n" + "="*50)
    print("       END OF REPORT")
    print("="*50 + "\n")


if __name__ == "__main__":
    main()
