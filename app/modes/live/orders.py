# app/modes/live/orders.py
"""
🔴 LIVE MODE - Выполнение реальных ордеров.
"""

from typing import Dict, List
from datetime import datetime
import schwabdev

from app.core.logger import logger
from app.core.sync_common import (
    get_notification_settings,
    play_error_sound,
    extract_order_id
)
from app.core.notification_service import get_notification_service


def execute_orders(
    client: schwabdev.Client,
    account_hash: str,
    deltas: Dict[str, int],
    prices: Dict[str, float]
) -> List[Dict]:
    """
    Выполнить реальные ордера (LIVE MODE) с обработкой ошибок.
    
    Args:
        client: schwabdev.Client для клиентского аккаунта
        account_hash: Hash аккаунта
        deltas: Dict {symbol: quantity} (положительный = BUY, отрицательный = SELL)
        prices: Dict {symbol: price}
        
    Returns:
        List[Dict] с результатами каждого ордера
    """
    from app.core.error_handler import (
        RetryHandler, ErrorTracker, get_error_settings
    )
    
    logger.info(f"[ORDER] 🔴 Executing {len(deltas)} LIVE orders...")
    
    # Получить настройки
    error_settings = get_error_settings()
    retry_handler = RetryHandler(max_retries=error_settings['retry_count'])
    error_tracker = ErrorTracker(max_errors=error_settings['max_errors_per_session'])
    notif_settings = get_notification_settings()
    
    results = []

    for symbol, delta in deltas.items():
        # Проверить нужно ли остановиться
        if error_tracker.should_stop(error_settings['stop_on_critical']):
            logger.error(f"🛑 Stopping order execution due to critical errors")
            # Добавить оставшиеся ордера как пропущенные
            remaining = {k: v for k, v in deltas.items() if k not in [r['symbol'] for r in results]}
            for sym, d in remaining.items():
                results.append({
                    'symbol': sym,
                    'action': "BUY" if d > 0 else "SELL",
                    'quantity': abs(d),
                    'price': prices.get(sym, 0),
                    'status': 'SKIPPED',
                    'error': 'Stopped due to critical errors',
                    'timestamp': datetime.now().isoformat()
                })
            break
        
        # Определить action и quantity
        action = "BUY" if delta > 0 else "SELL"
        quantity = abs(delta)

        # Функция для отправки ордера
        def place_order():
            if action == "BUY":
                from schwab.orders.equities import equity_buy_market
                order = equity_buy_market(symbol, quantity).build()
            else:
                from schwab.orders.equities import equity_sell_market
                order = equity_sell_market(symbol, quantity).build()
            return client.order_place(account_hash, order)

        # Выполнить с retry
        response, api_error = retry_handler.execute_with_retry(
            place_order,
            symbol=symbol
        )

        if api_error is None:
            # Успех
            order_id = extract_order_id(response)
            error_tracker.add_success()
            
            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': prices.get(symbol, 0),
                'status': 'SUCCESS',
                'order_id': order_id,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"[WORKER] [Order] {order_id} {action}/{symbol}/{quantity}/${prices.get(symbol, 0):.2f}")
            
            # Toast уведомление (если toast_on_success включен)
            if notif_settings['toast_on_success']:
                notif = get_notification_service()
                notif.order_success(symbol, action, quantity)
        else:
            # Ошибка
            error_tracker.add_error(api_error)
            
            results.append({
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': prices.get(symbol, 0),
                'status': 'ERROR',
                'error': api_error.message,
                'error_type': api_error.error_type.value,
                'error_code': api_error.code,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.error(f"[WORKER] [Order] ERROR {action}/{symbol}/{quantity}: {api_error.message}")
            
            # Toast уведомление об ошибке (если toast_on_error включен)
            if notif_settings['toast_on_error']:
                notif = get_notification_service()
                notif.order_error(symbol, action, api_error.message)
            
            # Звук при ошибке (если sound_on_error включен)
            if notif_settings['sound_on_error']:
                play_error_sound()
    
    # Логировать сводку ошибок
    error_summary = error_tracker.get_summary()
    if error_summary['total_errors'] > 0:
        logger.warning(f"[ORDER] ⚠️ Order execution completed with {error_summary['total_errors']} errors")
    
    return results
