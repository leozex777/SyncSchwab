
# cancel_pending_orders.py
# scripts.cancel_pending_orders

# Отмена всех ожидающих исполнения ордеров
# python scripts/cancel_pending_orders.py

import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
from app.core.config import build_client_for_slave
from app.gui.utils.env_manager import load_client_from_env

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

for acc in accounts:
    if acc.get('accountNumber') == '57876941':  # Luba account
        account_hash = acc.get('hashValue')
        break

if not account_hash:
    print("❌ Account hash not found!")
    exit(1)

print(f"Account hash: {account_hash[:8]}...")

# Получить ордера за последние 7 дней
from_time = datetime.now() - timedelta(days=7)
to_time = datetime.now()

orders = client.account_orders_all(
    fromEnteredTime=from_time,
    toEnteredTime=to_time
).json()

print(f"\nTotal orders: {len(orders)}")
print("=" * 50)

# Отменить PENDING ордера
pending_statuses = ['PENDING_ACTIVATION', 'QUEUED', 'WORKING', 'AWAITING_PARENT_ORDER']
cancelled_count = 0

for order in orders:
    status = order.get('status', 'UNKNOWN')
    order_id = order.get('orderId')
    
    legs = order.get('orderLegCollection', [])
    symbol = legs[0].get('instrument', {}).get('symbol', 'N/A') if legs else 'N/A'
    action = legs[0].get('instruction', 'N/A') if legs else 'N/A'
    qty = legs[0].get('quantity', 0) if legs else 0
    
    if status in pending_statuses:
        print(f"\n🔴 Cancelling Order ID: {order_id}")
        print(f"   {action} {qty} {symbol}")
        print(f"   Status: {status}")
        
        try:
            response = client.order_cancel(account_hash, order_id)
            
            if response.status_code in [200, 201, 204]:
                print(f"   ✅ CANCELLED successfully!")
                cancelled_count += 1
            else:
                print(f"   ❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print(f"\n⏭️ Skipping Order ID: {order_id} (Status: {status})")

print("\n" + "=" * 50)
print(f"✅ Cancelled {cancelled_count} orders")
print("=" * 50)
