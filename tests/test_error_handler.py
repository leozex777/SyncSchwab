
# test_error_handler.py
# tests/test_error_handler.py
#
# Запуск: python -m pytest tests/test_error_handler.py -v
# Или просто: python tests/test_error_handler.py

import sys
from unittest.mock import Mock
from app.core.error_handler import (
    ErrorType, ErrorSeverity, APIError,
    ErrorClassifier, RetryHandler, ErrorTracker,
    )

# Добавить путь к app (если запускаем напрямую)
sys.path.insert(0, '.')


class Colors:
    """ANSI цвета для терминала"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")


def print_test(name: str, passed: bool, details: str = ""):
    status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if passed else f"{Colors.RED}❌ FAIL{Colors.RESET}"
    print(f"  {status} {name}")
    if details and not passed:
        print(f"       {Colors.YELLOW}{details}{Colors.RESET}")


def print_section(name: str):
    print(f"\n{Colors.YELLOW}▶ {name}{Colors.RESET}")


# ════════════════════════════════════════════════════════════════
# ТЕСТЫ КЛАССИФИКАЦИИ ОШИБОК
# ════════════════════════════════════════════════════════════════

def test_classify_timeout():
    """Тест классификации timeout ошибки"""
    error = TimeoutError("Connection timed out")
    result = ErrorClassifier.classify(error, symbol="QLD")
    
    passed = (
        result.error_type == ErrorType.TIMEOUT and
        result.retryable is True and
        result.symbol == "QLD"
    )
    print_test("Timeout → TIMEOUT, retryable=True", passed, 
               f"Got: {result.error_type}, retryable={result.retryable}")
    return passed


def test_classify_network_error():
    """Тест классификации network ошибки"""
    error = ConnectionError("Network connection failed")
    result = ErrorClassifier.classify(error, symbol="SSO")
    
    passed = (
        result.error_type == ErrorType.NETWORK_ERROR and
        result.retryable is True
    )
    print_test("ConnectionError → NETWORK_ERROR, retryable=True", passed,
               f"Got: {result.error_type}, retryable={result.retryable}")
    return passed


def test_classify_401():
    """Тест классификации 401 Unauthorized"""
    error = Exception("HTTP Error")
    response = Mock()
    response.status_code = 401
    response.text = "Unauthorized"
    
    result = ErrorClassifier.classify(error, response=response, symbol="TQQQ")
    
    passed = (
        result.error_type == ErrorType.UNAUTHORIZED and
        result.severity == ErrorSeverity.CRITICAL and
        result.retryable is False
    )
    print_test("401 → UNAUTHORIZED, CRITICAL, retryable=False", passed,
               f"Got: {result.error_type}, {result.severity}, retryable={result.retryable}")
    return passed


def test_classify_429():
    """Тест классификации 429 Rate Limit"""
    error = Exception("HTTP Error")
    response = Mock()
    response.status_code = 429
    response.text = "Too many requests"
    
    result = ErrorClassifier.classify(error, response=response)
    
    passed = (
        result.error_type == ErrorType.RATE_LIMIT and
        result.retryable is True
    )
    print_test("429 → RATE_LIMIT, retryable=True", passed,
               f"Got: {result.error_type}, retryable={result.retryable}")
    return passed


def test_classify_500():
    """Тест классификации 500 Server Error"""
    error = Exception("HTTP Error")
    response = Mock()
    response.status_code = 500
    response.text = "Internal Server Error"
    
    result = ErrorClassifier.classify(error, response=response)
    
    passed = (
        result.error_type == ErrorType.SERVER_ERROR and
        result.retryable is True
    )
    print_test("500 → SERVER_ERROR, retryable=True", passed,
               f"Got: {result.error_type}, retryable={result.retryable}")
    return passed


def test_classify_400_insufficient_funds():
    """Тест классификации 400 с insufficient funds"""
    error = Exception("HTTP Error")
    response = Mock()
    response.status_code = 400
    response.text = "Insufficient funds for this order"
    
    result = ErrorClassifier.classify(error, response=response, symbol="QLD")
    
    passed = (
        result.error_type == ErrorType.INSUFFICIENT_FUNDS and
        result.retryable is False
    )
    print_test("400 + 'insufficient funds' → INSUFFICIENT_FUNDS", passed,
               f"Got: {result.error_type}")
    return passed


def test_classify_400_rejected():
    """Тест классификации 400 с rejected"""
    error = Exception("HTTP Error")
    response = Mock()
    response.status_code = 400
    response.text = "Order rejected by exchange"
    
    result = ErrorClassifier.classify(error, response=response)
    
    passed = (
        result.error_type == ErrorType.ORDER_REJECTED and
        result.retryable is False
    )
    print_test("400 + 'rejected' → ORDER_REJECTED", passed,
               f"Got: {result.error_type}")
    return passed


# ════════════════════════════════════════════════════════════════
# ТЕСТЫ RETRY HANDLER
# ════════════════════════════════════════════════════════════════

def test_retry_success_first_attempt():
    """Тест успешного выполнения с первой попытки"""
    handler = RetryHandler(max_retries=3, base_delay=0.01)
    
    call_count = 0

    def success_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result, error = handler.execute_with_retry(success_func, symbol="QLD")
    
    passed = (
        result == "success" and
        error is None and
        call_count == 1
    )
    print_test("Success on first attempt → 1 call, no error", passed,
               f"Got: result={result}, calls={call_count}")
    return passed


def test_retry_success_after_failures():
    """Тест успешного выполнения после нескольких ошибок"""
    handler = RetryHandler(max_retries=3, base_delay=0.01)
    
    call_count = 0

    def fail_then_success():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("Connection timed out")
        return "success"
    
    result, error = handler.execute_with_retry(fail_then_success, symbol="QLD")
    
    passed = (
        result == "success" and
        error is None and
        call_count == 3
    )
    print_test("Success after 2 failures → 3 calls total", passed,
               f"Got: result={result}, calls={call_count}")
    return passed


def test_retry_all_attempts_fail():
    """Тест когда все попытки неудачны"""
    handler = RetryHandler(max_retries=2, base_delay=0.01)
    
    call_count = 0

    def always_fail():
        nonlocal call_count
        call_count += 1
        raise TimeoutError("Connection timed out")
    
    result, error = handler.execute_with_retry(always_fail, symbol="QLD")
    
    passed = (
        result is None and
        error is not None and
        error.error_type == ErrorType.TIMEOUT and
        call_count == 3  # 1 initial + 2 retries
    )
    print_test("All 3 attempts fail → error returned", passed,
               f"Got: error={error.error_type if error else None}, calls={call_count}")
    return passed


def test_retry_non_retryable_error():
    """Тест, что non-retryable ошибки не повторяются"""
    handler = RetryHandler(max_retries=3, base_delay=0.01)
    
    call_count = 0

    def auth_error():
        nonlocal call_count
        call_count += 1
        # Симулируем 401 ошибку через текст
        raise Exception("unauthorized access denied")
    
    result, error = handler.execute_with_retry(auth_error, symbol="QLD")
    
    passed = (
        result is None and
        error is not None and
        call_count == 1  # Только одна попытка, retry не делается
    )
    print_test("Non-retryable error → only 1 attempt", passed,
               f"Got: calls={call_count}, error={error.error_type if error else None}")
    return passed


# ════════════════════════════════════════════════════════════════
# ТЕСТЫ ERROR TRACKER
# ════════════════════════════════════════════════════════════════

def test_tracker_counts_errors():
    """Тест подсчёта ошибок"""
    tracker = ErrorTracker(max_errors=5)
    
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    
    summary = tracker.get_summary()
    
    passed = (
        summary['total_errors'] == 2 and
        summary['consecutive_errors'] == 2
    )
    print_test("2 errors added → total=2, consecutive=2", passed,
               f"Got: total={summary['total_errors']}, consecutive={summary['consecutive_errors']}")
    return passed


def test_tracker_resets_consecutive_on_success():
    """Тест сброса consecutive при успехе"""
    tracker = ErrorTracker(max_errors=5)
    
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    tracker.add_success()
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    
    summary = tracker.get_summary()
    
    passed = (
        summary['total_errors'] == 3 and
        summary['consecutive_errors'] == 1
    )
    print_test("Success resets consecutive errors", passed,
               f"Got: total={summary['total_errors']}, consecutive={summary['consecutive_errors']}")
    return passed


def test_tracker_critical_error():
    """Тест обнаружения критической ошибки"""
    tracker = ErrorTracker(max_errors=5)
    
    tracker.add_error(APIError(ErrorType.UNAUTHORIZED, ErrorSeverity.CRITICAL, "Auth failed"))
    
    passed = tracker.is_critical() is True
    print_test("CRITICAL error → is_critical=True", passed,
               f"Got: is_critical={tracker.is_critical()}")
    return passed


def test_tracker_should_stop():
    """Тест логики остановки"""
    tracker = ErrorTracker(max_errors=5)
    
    # Добавить 3 последовательные ошибки
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    tracker.add_error(APIError(ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, "Timeout"))
    
    # С stop_on_critical=False не должен останавливаться
    should_stop_false = tracker.should_stop(stop_on_critical=False)
    
    # С stop_on_critical=True должен остановиться (3+ consecutive)
    should_stop_true = tracker.should_stop(stop_on_critical=True)
    
    passed = (
        should_stop_false is False and
        should_stop_true is True
    )
    print_test("3 consecutive errors + stop_on_critical → should_stop", passed,
               f"Got: stop_on_critical=False → {should_stop_false}, =True → {should_stop_true}")
    return passed


def test_tracker_reset():
    """Тест сброса трекера"""
    tracker = ErrorTracker(max_errors=5)
    
    tracker.add_error(APIError(ErrorType.UNAUTHORIZED, ErrorSeverity.CRITICAL, "Auth failed"))
    tracker.reset()
    
    summary = tracker.get_summary()
    
    passed = (
        summary['total_errors'] == 0 and
        tracker.is_critical() is False
    )
    print_test("Reset clears all errors", passed,
               f"Got: total={summary['total_errors']}, is_critical={tracker.is_critical()}")
    return passed


# ════════════════════════════════════════════════════════════════
# ТЕСТЫ API ERROR
# ════════════════════════════════════════════════════════════════

def test_api_error_to_dict():
    """Тест сериализации APIError в dict"""
    error = APIError(
        error_type=ErrorType.TIMEOUT,
        severity=ErrorSeverity.MEDIUM,
        message="Connection timed out",
        code="ETIMEDOUT",
        symbol="QLD",
        retryable=True
    )
    
    result = error.to_dict()
    
    passed = (
        result['error_type'] == 'timeout' and
        result['severity'] == 'medium' and
        result['symbol'] == 'QLD' and
        result['retryable'] is True
    )
    print_test("APIError.to_dict() serializes correctly", passed,
               f"Got: {result}")
    return passed


# ════════════════════════════════════════════════════════════════
# ЗАПУСК ВСЕХ ТЕСТОВ
# ════════════════════════════════════════════════════════════════

def run_all_tests():
    """Запустить все тесты"""
    print_header("ERROR HANDLER UNIT TESTS")
    
    results = []
    
    # Classification tests
    print_section("Error Classification")
    results.append(test_classify_timeout())
    results.append(test_classify_network_error())
    results.append(test_classify_401())
    results.append(test_classify_429())
    results.append(test_classify_500())
    results.append(test_classify_400_insufficient_funds())
    results.append(test_classify_400_rejected())
    
    # Retry handler tests
    print_section("Retry Handler")
    results.append(test_retry_success_first_attempt())
    results.append(test_retry_success_after_failures())
    results.append(test_retry_all_attempts_fail())
    results.append(test_retry_non_retryable_error())
    
    # Error tracker tests
    print_section("Error Tracker")
    results.append(test_tracker_counts_errors())
    results.append(test_tracker_resets_consecutive_on_success())
    results.append(test_tracker_critical_error())
    results.append(test_tracker_should_stop())
    results.append(test_tracker_reset())
    
    # API Error tests
    print_section("API Error")
    results.append(test_api_error_to_dict())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print_header("SUMMARY")
    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}All {total} tests passed! ✅{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}{passed}/{total} tests passed{Colors.RESET}")
        print(f"{Colors.RED}Failed: {total - passed}{Colors.RESET}")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
