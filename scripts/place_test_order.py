# place_test_order.py
# scripts/place_test_order.py

"""
Размещение тестового ордера на 1 акцию.

⚠️ ВНИМАНИЕ: Это РЕАЛЬНЫЙ ордер!

Запуск: python scripts/place_test_order.py
"""

import sys
import os

# Добавить корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import build_client_for_slave
from app.gui.utils.env_manager import load_client_from_env

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ ОРДЕРА
# ═══════════════════════════════════════════════════════════════

CLIENT_ID = "slave_1"
SYMBOL = "SSO"          # Символ акции
QUANTITY = 1            # Количество
ACTION = "BUY"          # BUY или SELL
ORDER_TYPE = "MARKET"   # MARKET или LIMIT
DURATION = "DAY"        # DAY - действует до конца дня

# ═══════════════════════════════════════════════════════════════
# ПОДКЛЮЧЕНИЕ
# ═══════════════════════════════════════════════════════════════

print("=" * 60)
print("🛒 PLACE TEST ORDER")
print("=" * 60)
print(f"Client: {CLIENT_ID}")
print(f"Symbol: {SYMBOL}")
print(f"Quantity: {QUANTITY}")
print(f"Action: {ACTION}")
print(f"Order Type: {ORDER_TYPE}")
print(f"Duration: {DURATION}")
print("=" * 60)

# Подтверждение
confirm = input("\n⚠️ This is a REAL order! Continue? (yes/no): ")
if confirm.lower() != 'yes':
    print("❌ Cancelled")
    sys.exit(0)

# Создать клиент
env_data = load_client_from_env(CLIENT_ID)
client = build_client_for_slave(
    CLIENT_ID,
    env_data['key_id'],
    env_data['client_secret'],
    env_data.get('redirect_uri', 'https://127.0.0.1:8182')
)

# ═══════════════════════════════════════════════════════════════
# ПОЛУЧИТЬ ACCOUNT HASH
# ═══════════════════════════════════════════════════════════════

accounts = client.account_linked().json()
account_hash = None

for acc in accounts:
    account_hash = acc.get('hashValue')
    account_number = acc.get('accountNumber')
    print(f"\n📋 Found account: {account_number}")
    break

if not account_hash:
    print("❌ Account hash not found!")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# СОЗДАТЬ ОРДЕР
# ═══════════════════════════════════════════════════════════════

order = {
    "orderType": ORDER_TYPE,
    "session": "NORMAL",
    "duration": DURATION,
    "orderStrategyType": "SINGLE",
    "orderLegCollection": [
        {
            "instruction": ACTION,
            "quantity": QUANTITY,
            "instrument": {
                "symbol": SYMBOL,
                "assetType": "EQUITY"
            }
        }
    ]
}

print(f"\n📤 Placing order...")
print(f"   {ACTION} {QUANTITY} {SYMBOL} @ {ORDER_TYPE}")

try:
    response = client.order_place(account_hash, order)
    
    if response.status_code in [200, 201]:
        # Получить Order ID из заголовка Location
        location = response.headers.get('Location', '')
        order_id = location.split('/')[-1] if location else 'N/A'
        
        print(f"\n✅ ORDER PLACED SUCCESSFULLY!")
        print(f"   Order ID: {order_id}")
        print(f"   Status Code: {response.status_code}")
    else:
        print(f"\n❌ ORDER FAILED!")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")

print("\n" + "=" * 60)
