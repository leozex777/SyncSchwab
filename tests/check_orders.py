
# check_orders.py
# tests.check_orders

# python tests/check_orders.py

from datetime import datetime, timedelta
import sys

sys.path.insert(0, '.')

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

# Временной диапазон: последние 7 дней
from_time = datetime.now() - timedelta(days=7)
to_time = datetime.now()

# Получить все ордера (правильные имена параметров)
orders = client.account_orders_all(
    fromEnteredTime=from_time,
    toEnteredTime=to_time
).json()

print(f"Total orders: {len(orders)}")
print("=" * 50)

if not orders:
    print("No orders found")
else:
    for order in orders:
        status = order.get('status', 'UNKNOWN')
        order_id = order.get('orderId', 'N/A')
        entered = order.get('enteredTime', '')[:19]

        legs = order.get('orderLegCollection', [])
        for leg in legs:
            symbol = leg.get('instrument', {}).get('symbol', 'N/A')
            action = leg.get('instruction', 'N/A')
            qty = leg.get('quantity', 0)

            print(f"Order ID: {order_id}")
            print(f"  {action} {qty} {symbol}")
            print(f"  Status: {status}")
            print(f"  Entered: {entered}")
            print("-" * 30)

# Добавить в конец check_orders.py:

# Отменить все PENDING ордера
# for order in orders:
#     if order.get('status') in ['PENDING_ACTIVATION', 'QUEUED', 'WORKING']:
#         order_id = order.get('orderId')
#         account_hash = "ВАШ_HASH"  # Получить из account_linked()
#
#         print(f"Cancelling order {order_id}...")
#         client.order_cancel(account_hash, order_id)
#         print(f"  ✅ Cancelled")