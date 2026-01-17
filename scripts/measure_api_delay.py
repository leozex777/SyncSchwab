# measure_api_delay.py
# scripts/measure_api_delay.py

"""
Измерение задержки Schwab API.

Скрипт опрашивает API каждые N секунд и записывает:
- Когда появились ордера
- Когда появились позиции
- Задержку от времени открытия рынка (9:30 ET)

Запуск: python scripts/measure_api_delay.py
"""

import sys
import os
import time
from datetime import datetime, timedelta

# Добавить корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import build_client_for_slave
from app.gui.utils.env_manager import load_client_from_env

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════

CLIENT_ID = "slave_1"
POLL_INTERVAL = 5  # Опрашивать каждые N секунд
MARKET_OPEN_TIME = "09:30:00"  # Время открытия рынка (ET)

# Какие символы ожидаем (из ваших ордеров)
EXPECTED_SYMBOLS = ["SSO"]

# ═══════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════

print("=" * 60)
print("📊 SCHWAB API DELAY MEASUREMENT")
print("=" * 60)
print(f"Client: {CLIENT_ID}")
print(f"Poll interval: {POLL_INTERVAL} seconds")
print(f"Expected symbols: {EXPECTED_SYMBOLS}")
print(f"Market open: {MARKET_OPEN_TIME} ET")
print("=" * 60)

# Создать клиент
env_data = load_client_from_env(CLIENT_ID)
client = build_client_for_slave(
    CLIENT_ID,
    env_data['key_id'],
    env_data['client_secret'],
    env_data.get('redirect_uri', 'https://127.0.0.1:8182')
)

# Получить account_hash (как в cache_manager!)
accounts_linked = client.account_linked().json()
account_hash = None
account_number = None

for acc in accounts_linked:
    account_hash = acc.get('hashValue')
    account_number = acc.get('accountNumber')
    break

if not account_hash:
    print("❌ Account hash not found!")
    sys.exit(1)

print(f"Account: {account_number}")

# Импортировать парсер позиций
from app.models.copier.entities import parse_positions_from_account_details

# Состояние
orders_found_time = None
positions_found_time = None
start_time = datetime.now()

# Парсить время открытия рынка (сегодня)
today = datetime.now().date()
market_open = datetime.strptime(f"{today} {MARKET_OPEN_TIME}", "%Y-%m-%d %H:%M:%S")

print(f"\n🕐 Started at: {start_time.strftime('%H:%M:%S')}")
print(f"🔔 Market opens at: {market_open.strftime('%H:%M:%S')}")
print(f"\n⏳ Polling API... (Ctrl+C to stop)\n")

# ═══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════

poll_count = 0

try:
    while True:
        poll_count += 1
        now = datetime.now()
        time_str = now.strftime('%H:%M:%S')
        
        # ─── Проверить ордера ───
        orders_status = "❌"
        found_order_symbols = []
        
        try:
            from datetime import timedelta as td
            from_time = datetime.now() - td(days=1)
            to_time = datetime.now()
            
            orders = client.account_orders_all(
                fromEnteredTime=from_time,
                toEnteredTime=to_time
            ).json()
            
            for order in orders:
                legs = order.get('orderLegCollection', [])
                for leg in legs:
                    symbol = leg.get('instrument', {}).get('symbol', '')
                    if symbol in EXPECTED_SYMBOLS:
                        found_order_symbols.append(symbol)
                        status = order.get('status', 'UNKNOWN')
                        
            if found_order_symbols:
                orders_status = f"✅ {len(found_order_symbols)} ({', '.join(set(found_order_symbols))})"
                if orders_found_time is None:
                    orders_found_time = now
                    print(f"\n🎯 ORDERS FOUND at {time_str}!")
                    if now > market_open:
                        delay = (now - market_open).total_seconds()
                        print(f"   Delay from market open: {delay:.0f} seconds ({delay/60:.1f} min)")
                    print()
                    
        except Exception as e:
            orders_status = f"⚠️ Error: {e}"
        
        # ─── Проверить позиции ───
        positions_status = "❌"
        found_position_symbols = []
        
        try:
            # Использовать правильный метод (как в cache_manager!)
            details = client.account_details(account_hash, fields='positions').json()
            positions = parse_positions_from_account_details(details)
            
            for pos in positions:
                if pos.symbol in EXPECTED_SYMBOLS and pos.quantity > 0:
                    found_position_symbols.append(f"{pos.symbol}:{pos.quantity}")
                        
            if found_position_symbols:
                positions_status = f"✅ {', '.join(found_position_symbols)}"
                if positions_found_time is None:
                    positions_found_time = now
                    print(f"\n🎯 POSITIONS FOUND at {time_str}!")
                    if now > market_open:
                        delay = (now - market_open).total_seconds()
                        print(f"   Delay from market open: {delay:.0f} seconds ({delay/60:.1f} min)")
                    print()
            else:
                positions_status = f"❌ (total: {len(positions)})"
                        
        except Exception as e:
            positions_status = f"⚠️ Error: {e}"
        
        # ─── Вывод статуса ───
        elapsed = (now - start_time).total_seconds()
        
        # Время до/после открытия рынка
        if now < market_open:
            market_diff = (market_open - now).total_seconds()
            market_str = f"T-{market_diff:.0f}s"
        else:
            market_diff = (now - market_open).total_seconds()
            market_str = f"T+{market_diff:.0f}s"
        
        print(f"[{time_str}] #{poll_count:3d} | {market_str:>8} | Orders: {orders_status:<25} | Positions: {positions_status}")
        
        # ─── Проверить завершение ───
        if orders_found_time and positions_found_time:
            print("\n" + "=" * 60)
            print("✅ ALL DATA FOUND!")
            print("=" * 60)
            print(f"Orders appeared at:    {orders_found_time.strftime('%H:%M:%S')}")
            print(f"Positions appeared at: {positions_found_time.strftime('%H:%M:%S')}")
            
            if orders_found_time > market_open:
                print(f"Orders delay:          {(orders_found_time - market_open).total_seconds():.0f} seconds")
            if positions_found_time > market_open:
                print(f"Positions delay:       {(positions_found_time - market_open).total_seconds():.0f} seconds")
            
            print("=" * 60)
            break
        
        # Ждать
        time.sleep(POLL_INTERVAL)
        
except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print("⏹️ STOPPED BY USER")
    print("=" * 60)
    print(f"Total polls: {poll_count}")
    print(f"Total time: {(datetime.now() - start_time).total_seconds():.0f} seconds")
    
    if orders_found_time:
        print(f"Orders found at: {orders_found_time.strftime('%H:%M:%S')}")
    else:
        print("Orders: NOT FOUND")
        
    if positions_found_time:
        print(f"Positions found at: {positions_found_time.strftime('%H:%M:%S')}")
    else:
        print("Positions: NOT FOUND")
    
    print("=" * 60)
