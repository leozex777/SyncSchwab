
# order_simulator.py
# tests/order_simulator.py
#
# Симулятор ордеров для тестирования error_handler
# Запуск: python tests/order_simulator.py
#
# Симулирует разные сценарии:
# - Все успешно
# - Случайные ошибки
# - Timeout
# - Rate limit
# - Unauthorized
# - Insufficient funds

import sys
import random
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass
from app.core.error_handler import (
    RetryHandler, ErrorTracker, get_error_settings
    )

# Добавить путь к app
sys.path.insert(0, '.')


class Colors:
    """ANSI цвета для терминала"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class SimulationMode(Enum):
    """Режимы симуляции"""
    ALL_SUCCESS = "all_success"           # Все ордера успешны
    RANDOM_ERRORS = "random_errors"       # Случайные ошибки (30%)
    ALL_TIMEOUT = "all_timeout"           # Все timeout
    ALL_REJECTED = "all_rejected"         # Все отклонены
    RATE_LIMIT = "rate_limit"             # Rate limit после 3 ордеров
    UNAUTHORIZED = "unauthorized"         # 401 на первом ордере
    INSUFFICIENT_FUNDS = "insufficient"   # Недостаточно средств
    MIXED_SCENARIO = "mixed"              # Смешанный сценарий


@dataclass
class SimulatedOrder:
    """Симулированный ордер"""
    symbol: str
    action: str  # BUY / SELL
    quantity: int
    price: float
    status: str  # SUCCESS / ERROR / SKIPPED
    order_id: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    attempts: int = 1
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class OrderSimulator:
    """Симулятор ордеров"""
    
    def __init__(self, mode: SimulationMode = SimulationMode.RANDOM_ERRORS):
        self.mode = mode
        self.order_count = 0
        self.error_settings = get_error_settings()
        self.retry_handler = RetryHandler(
            max_retries=self.error_settings['retry_count'],
            base_delay=0.5  # Быстрее для симуляции
        )
        self.error_tracker = ErrorTracker(
            max_errors=self.error_settings['max_errors_per_session']
        )
        
        # Статистика
        self.stats = {
            'total_orders': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'total_attempts': 0
        }

    @staticmethod
    def _generate_order_id() -> str:
        """Генерировать фейковый order ID"""
        return f"SIM-{random.randint(100000, 999999)}"
    
    def _simulate_api_call(self, symbol: str, action: str, quantity: int):
        """
        Симулировать API вызов с разными результатами.
        
        Raises:
            Exception: В зависимости от режима симуляции
        """
        self.order_count += 1
        
        if self.mode == SimulationMode.ALL_SUCCESS:
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        elif self.mode == SimulationMode.ALL_TIMEOUT:
            raise TimeoutError("Connection timed out")
        
        elif self.mode == SimulationMode.ALL_REJECTED:
            raise Exception("Order rejected by exchange")
        
        elif self.mode == SimulationMode.RATE_LIMIT:
            if self.order_count > 3:
                raise Exception("Rate limit exceeded (429)")
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        elif self.mode == SimulationMode.UNAUTHORIZED:
            if self.order_count == 1:
                raise Exception("Unauthorized access (401)")
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        elif self.mode == SimulationMode.INSUFFICIENT_FUNDS:
            if action == "BUY":
                raise Exception("Insufficient funds for order")
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        elif self.mode == SimulationMode.RANDOM_ERRORS:
            if random.random() < 0.3:  # 30% chance of error
                error_type = random.choice([
                    "timeout",
                    "rejected",
                    "server_error"
                ])
                if error_type == "timeout":
                    raise TimeoutError("Connection timed out")
                elif error_type == "rejected":
                    raise Exception("Order rejected")
                else:
                    raise Exception("Internal server error (500)")
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        elif self.mode == SimulationMode.MIXED_SCENARIO:
            # Сценарий: 1-успех, 2-timeout(retry), 3-успех, 4-rejected, 5-успех
            scenarios = {
                1: "success",
                2: "timeout",  # Будет retry
                3: "success",
                4: "rejected",
                5: "success"
            }
            scenario = scenarios.get(self.order_count, "success")
            
            if scenario == "timeout":
                # 50% шанс успеха при retry
                if random.random() < 0.5:
                    raise TimeoutError("Connection timed out")
            elif scenario == "rejected":
                raise Exception("Order rejected by exchange")
            
            return {"order_id": self._generate_order_id(), "status": "FILLED"}
        
        # Default: success
        return {"order_id": self._generate_order_id(), "status": "FILLED"}
    
    def execute_order(self, symbol: str, action: str, quantity: int, price: float) -> SimulatedOrder:
        """
        Выполнить симулированный ордер с retry логикой.
        """
        self.stats['total_orders'] += 1
        
        # Проверить нужно ли остановиться
        if self.error_tracker.should_stop(self.error_settings['stop_on_critical']):
            self.stats['skipped'] += 1
            return SimulatedOrder(
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                status="SKIPPED",
                error="Stopped due to critical errors"
            )
        
        # Функция для retry
        attempts = [0]  # Использовать список, чтобы изменять в closure

        def place_order():
            attempts[0] += 1
            return self._simulate_api_call(symbol, action, quantity)
        
        # Выполнить с retry
        result, api_error = self.retry_handler.execute_with_retry(
            place_order,
            symbol=symbol
        )
        
        self.stats['total_attempts'] += attempts[0]
        
        if api_error is None:
            # Успех
            self.error_tracker.add_success()
            self.stats['successful'] += 1
            
            return SimulatedOrder(
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                status="SUCCESS",
                order_id=result.get('order_id'),
                attempts=attempts[0]
            )
        else:
            # Ошибка
            self.error_tracker.add_error(api_error)
            self.stats['failed'] += 1
            
            return SimulatedOrder(
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                status="ERROR",
                error=api_error.message,
                error_type=api_error.error_type.value,
                attempts=attempts[0]
            )
    
    def execute_orders(self, deltas: Dict[str, int], prices: Dict[str, float]) -> List[SimulatedOrder]:
        """
        Выполнить список ордеров.
        """
        results = []
        
        for symbol, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            quantity = abs(delta)
            price = prices.get(symbol, 100.0)
            
            order = self.execute_order(symbol, action, quantity, price)
            results.append(order)
        
        return results
    
    def get_stats(self) -> dict:
        """Получить статистику"""
        return {
            **self.stats,
            'error_summary': self.error_tracker.get_summary()
        }
    
    def reset(self):
        """Сбросить симулятор"""
        self.order_count = 0
        self.error_tracker.reset()
        self.stats = {
            'total_orders': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'total_attempts': 0
        }


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")


def print_order(order: SimulatedOrder):
    """Красиво вывести ордер"""
    if order.status == "SUCCESS":
        status_color = Colors.GREEN
        status_icon = "✅"
    elif order.status == "SKIPPED":
        status_color = Colors.YELLOW
        status_icon = "⏭️"
    else:
        status_color = Colors.RED
        status_icon = "❌"
    
    action_color = Colors.GREEN if order.action == "BUY" else Colors.MAGENTA
    
    print(f"  {status_icon} {status_color}{order.status:8}{Colors.RESET} | "
          f"{action_color}{order.action:4}{Colors.RESET} {order.quantity:4} x {order.symbol:6} "
          f"@ ${order.price:>8.2f} = ${order.quantity * order.price:>10.2f}")
    
    if order.order_id:
        print(f"     {Colors.CYAN}Order ID: {order.order_id}{Colors.RESET}")
    
    if order.error:
        print(f"     {Colors.RED}Error: {order.error}{Colors.RESET}")
    
    if order.attempts > 1:
        print(f"     {Colors.YELLOW}Attempts: {order.attempts}{Colors.RESET}")


def print_stats(stats: dict):
    """Вывести статистику"""
    print(f"\n{Colors.BOLD}📊 Statistics:{Colors.RESET}")
    print(f"   Total Orders:   {stats['total_orders']}")
    print(f"   {Colors.GREEN}Successful:     {stats['successful']}{Colors.RESET}")
    print(f"   {Colors.RED}Failed:         {stats['failed']}{Colors.RESET}")
    print(f"   {Colors.YELLOW}Skipped:        {stats['skipped']}{Colors.RESET}")
    print(f"   Total Attempts: {stats['total_attempts']}")
    
    error_summary = stats.get('error_summary', {})
    if error_summary.get('total_errors', 0) > 0:
        print(f"\n{Colors.BOLD}⚠️ Error Summary:{Colors.RESET}")
        print(f"   Total Errors:      {error_summary['total_errors']}")
        print(f"   Consecutive:       {error_summary['consecutive_errors']}")
        print(f"   Critical:          {error_summary['is_critical']}")


def run_simulation(mode: SimulationMode, deltas: Dict[str, int], prices: Dict[str, float]):
    """Запустить симуляцию"""
    print_header(f"Simulation: {mode.value.upper()}")
    
    simulator = OrderSimulator(mode=mode)
    
    print(f"\n{Colors.BOLD}📋 Orders to execute:{Colors.RESET}")
    for symbol, delta in deltas.items():
        action = "BUY" if delta > 0 else "SELL"
        print(f"   {action} {abs(delta)} x {symbol} @ ${prices.get(symbol, 0):.2f}")
    
    print(f"\n{Colors.BOLD}🚀 Executing orders...{Colors.RESET}\n")
    
    results = simulator.execute_orders(deltas, prices)
    
    print(f"\n{Colors.BOLD}📝 Results:{Colors.RESET}")
    for order in results:
        print_order(order)
    
    print_stats(simulator.get_stats())
    
    return results


def run_all_simulations():
    """Запустить все симуляции"""
    # Тестовые данные
    deltas = {
        "QLD": 32,      # BUY 32
        "SSO": 128,     # BUY 128
        "TQQQ": -50,    # SELL 50
        "UPRO": 75,     # BUY 75
        "SPXL": -25     # SELL 25
    }
    
    prices = {
        "QLD": 85.50,
        "SSO": 92.30,
        "TQQQ": 65.75,
        "UPRO": 78.20,
        "SPXL": 145.00
    }
    
    print_header("ORDER SIMULATOR")
    print(f"\n{Colors.CYAN}This simulator tests error handling without real orders.{Colors.RESET}")
    print(f"{Colors.CYAN}Select a simulation mode to run:{Colors.RESET}\n")
    
    modes = list(SimulationMode)
    for i, mode in enumerate(modes, 1):
        print(f"  {i}. {mode.value}")
    print(f"  0. Run ALL simulations")
    print(f"  q. Quit")
    
    while True:
        choice = input(f"\n{Colors.BOLD}Select mode (0-{len(modes)}, q): {Colors.RESET}").strip().lower()
        
        if choice == 'q':
            print("Bye!")
            break
        
        try:
            choice_num = int(choice)
            
            if choice_num == 0:
                # Запустить все
                for mode in modes:
                    run_simulation(mode, deltas.copy(), prices.copy())
                    print("\n" + "-" * 70)
            elif 1 <= choice_num <= len(modes):
                mode = modes[choice_num - 1]
                run_simulation(mode, deltas.copy(), prices.copy())
            else:
                print(f"{Colors.RED}Invalid choice{Colors.RESET}")
                
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.RESET}")
        
        print()


if __name__ == "__main__":
    run_all_simulations()
