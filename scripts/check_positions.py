# check_positions.py
# scripts/check_positions.py

"""
Проверка позиций через API (как в cache_manager).

python scripts/check_positions.py

"""


import sys
import os

# Добавить корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import build_client_for_slave
from app.gui.utils.env_manager import load_client_from_env
from app.models.copier.entities import parse_positions_from_account_details

client_id = "slave_1"
env_data = load_client_from_env(client_id)

client = build_client_for_slave(
    client_id,
    env_data['key_id'],
    env_data['client_secret'],
    env_data.get('redirect_uri', 'https://127.0.0.1:8182')
)

# Получить account_hash
accounts = client.account_linked().json()
account_hash = None
account_number = None

for acc in accounts:
    account_hash = acc.get('hashValue')
    account_number = acc.get('accountNumber')
    break

if not account_hash:
    print("❌ Account hash not found!")
    sys.exit(1)

print(f"Account: {account_number}")
print(f"Hash: {account_hash[:8]}...")
print("=" * 50)

# Получить позиции (как в cache_manager!)
details = client.account_details(account_hash, fields='positions').json()
positions = parse_positions_from_account_details(details)

print(f"Positions: {len(positions)}")
print("-" * 50)

for pos in positions:
    print(f"  {pos.symbol}: {pos.quantity} @ ${pos.market_value/pos.quantity:.2f} = ${pos.market_value:.2f}")

print("=" * 50)
